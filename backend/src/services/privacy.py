import hashlib,json,math,time
from random import SystemRandom
from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from src.models.run import Run
from src.models.privacy import PrivacyBudget,PrivacyQuery
from src.services.audit import log
from src.constants.enums import EPSILON_LEVELS,PRIVACY_TOTAL_EPSILON,CONTRIBUTION_LIMIT_MINUTES
_rng=SystemRandom()
SENSITIVITY_MINUTES=2*CONTRIBUTION_LIMIT_MINUTES
TOLERANCE=1e-9
def laplace(scale):
 u=0.5-_rng.random()
 if u==0:return 0.0
 magnitude=max(1.0-2.0*abs(u),1e-15)
 return -scale*math.copysign(1,u)*math.log(magnitude)
def domain(run):
 sources=run.snapshot['sources']
 return sorted({s['period'] for s in sources}),sorted({s['department'] for s in sources})
def key_for(run_id,periods,departments,epsilon):
 canonical={'run':run_id,'periods':periods,'departments':departments,'epsilon':epsilon}
 return hashlib.sha256(json.dumps(canonical,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def bounded_sums(sources,periods,departments):
 pset,dset=set(periods),set(departments);good=planned=0.0
 for s in sources:
  if s['period'] in pset and s['department'] in dset:
   planned+=min(max(s['end']-s['start'],0),CONTRIBUTION_LIMIT_MINUTES)
   good+=min(max(s['good']*s['ideal_seconds']/60,0),CONTRIBUTION_LIMIT_MINUTES)
 return good,planned
def budget_card(budget):
 return {'total':budget.total,'spent':round(budget.spent,9),'remaining':round(max(budget.total-budget.spent,0),9)}
def mechanism_card():
 return {'name':'纯差分隐私 Laplace 机制','delta':0,'adjacency':'相邻数据：增加或删除一条设备日记录','contribution_limit_minutes':CONTRIBUTION_LIMIT_MINUTES,'sensitivity_minutes':SENSITIVITY_MINUTES,'composition':'同一报告的全部查询按 ε 顺序叠加，共享不可重置的预算；相同条件重试命中缓存不重复扣减','description':'每条设备日记录对“合格理想分钟”和“计划分钟”两个分量的贡献分别截断到上限后求和，向量查询 L1 敏感度 Δ=2×上限；两分量独立添加尺度 b=Δ/ε 的 Laplace 噪声（纯 ε-差分隐私，δ=0）。OEE 为噪声分量之比，属后处理，任何人可由公开的噪声分量重算。日期与设备名单视为公开目录，产量数值只以噪声分量发布。'}
def result_payload(noisy_good,noisy_planned,epsilon):
 scale=SENSITIVITY_MINUTES/epsilon
 return {'noisy_ideal_good_minutes':noisy_good,'noisy_planned_minutes':noisy_planned,'oee':noisy_good/noisy_planned if noisy_planned>0 else None,'mechanism':'纯差分隐私 Laplace 机制（δ=0）','adjacency':'相邻数据：增加或删除一条设备日记录','contribution_limit_minutes':CONTRIBUTION_LIMIT_MINUTES,'sensitivity_minutes':SENSITIVITY_MINUTES,'noise_scale_minutes':scale,'error_std_minutes':scale*math.sqrt(2),'error_p95_minutes':scale*math.log(20),'note':'OEE=噪声合格理想分钟÷噪声计划分钟，可由公开噪声分量直接重算；分量 95% 概率绝对误差不超误差界，命中设备日越多 OEE 相对误差越小；噪声计划分钟非正时 OEE 不可解释，请扩大筛选或提高 ε'}
def query_card(q):
 return {'id':q.id,'actor':q.actor,'request':q.request,'epsilon':q.epsilon,'status':q.status,'reason':q.reason,'result':q.result,'created':q.created}
def ensure_budget(db,run_id):
 budget=db.query(PrivacyBudget).filter_by(run_id=run_id).first()
 if budget:return budget
 try:
  with db.begin_nested():
   db.add(PrivacyBudget(run_id=run_id,total=PRIVACY_TOTAL_EPSILON,spent=0.0,created=time.time()));db.flush()
  return db.query(PrivacyBudget).filter_by(run_id=run_id).first()
 except IntegrityError:
  db.rollback()
  return db.query(PrivacyBudget).filter_by(run_id=run_id).first()
def get_run(db,run_id):
 run=db.get(Run,run_id)
 if not run:raise HTTPException(404,'报告不存在')
 if not run.approved:raise HTTPException(409,'隐私查询仅面向已复核报告')
 return run
def info(db,run_id):
 run=get_run(db,run_id)
 budget=ensure_budget(db,run.id);db.commit()
 periods,departments=domain(run)
 queries=db.query(PrivacyQuery).filter_by(run_id=run.id).order_by(PrivacyQuery.id.desc()).limit(100).all()
 return {'run_id':run.id,'run_name':run.name,'options':{'periods':periods,'departments':departments,'epsilons':list(EPSILON_LEVELS)},'budget':budget_card(budget),'mechanism':mechanism_card(),'queries':[query_card(q) for q in queries]}
def replay(db,existing):
 if existing.status=='completed':
  budget=ensure_budget(db,existing.run_id)
  return {'id':existing.id,'run_id':existing.run_id,'status':'completed','reused':True,'request':existing.request,'epsilon':existing.epsilon,'result':existing.result,'budget':budget_card(budget),'created':existing.created}
 raise HTTPException(409,existing.reason)
def reject(db,run,key,user,request,epsilon,reason):
 db.add(PrivacyQuery(run_id=run.id,dedupe_key=key,actor=user.email,request=request,epsilon=epsilon,status='rejected',reason=reason,created=time.time()))
 log(db,user.email,'privacy.rejected',f'报告{run.id} ε={epsilon}')
 try:db.commit()
 except IntegrityError:db.rollback()
 raise HTTPException(409,reason)
def query(db,user,run_id,body):
 run=get_run(db,run_id)
 all_periods,all_departments=domain(run)
 epsilon=float(body.epsilon)
 if epsilon not in EPSILON_LEVELS:raise ValueError('隐私强度 ε 须为档位 '+'/'.join(str(x) for x in EPSILON_LEVELS)+' 之一')
 periods=sorted(set(body.periods));departments=sorted(set(body.departments))
 unknown=[x for x in periods if x not in all_periods]+[x for x in departments if x not in all_departments]
 if unknown:raise ValueError('筛选超出报告快照范围：'+'、'.join(unknown))
 key=key_for(run.id,periods,departments,epsilon)
 existing=db.query(PrivacyQuery).filter_by(dedupe_key=key).first()
 if existing:return replay(db,existing)
 budget=ensure_budget(db,run.id)
 request={'periods':periods,'departments':departments,'epsilon':epsilon}
 if budget.spent+epsilon>budget.total+TOLERANCE:
  reject(db,run,key,user,request,epsilon,f'隐私预算不足：报告剩余 ε={round(max(budget.total-budget.spent,0),4)}，本次请求 ε={epsilon}；同一报告的预算跨账号共享且不可重置')
 good,planned=bounded_sums(run.snapshot['sources'],periods,departments)
 scale=SENSITIVITY_MINUTES/epsilon
 noisy_good,noisy_planned=good+laplace(scale),planned+laplace(scale)
 spent_before=budget.spent
 charged=db.execute(update(PrivacyBudget).where(PrivacyBudget.id==budget.id,PrivacyBudget.spent+epsilon<=PrivacyBudget.total+TOLERANCE).values(spent=PrivacyBudget.spent+epsilon)).rowcount
 if charged!=1:
  db.rollback()
  reject(db,run,key,user,request,epsilon,'隐私预算不足：并发扣减后剩余额度不够，本次未计费；预算跨账号共享且不可重置')
 row=PrivacyQuery(run_id=run.id,dedupe_key=key,actor=user.email,request=request,epsilon=epsilon,status='completed',reason='',result=result_payload(noisy_good,noisy_planned,epsilon),created=time.time())
 db.add(row);log(db,user.email,'privacy.query',f'报告{run.id} ε={epsilon}')
 try:db.commit()
 except IntegrityError:
  db.rollback()
  winner=db.query(PrivacyQuery).filter_by(dedupe_key=key).first()
  if winner:return replay(db,winner)
  raise
 return {'id':row.id,'run_id':run.id,'status':'completed','reused':False,'request':request,'epsilon':epsilon,'result':row.result,'budget':{'total':budget.total,'spent':round(spent_before+epsilon,9),'remaining':round(max(budget.total-spent_before-epsilon,0),9)},'created':row.created}
