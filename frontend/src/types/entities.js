// API实体字段约定：来源{id,natural_key,data}、口径{id,version,data}、报告{id,status,snapshot,checksum,result,approved}、计划{next_at,enabled}。隐私查询：GET /runs/{id}/privacy→{options,budget,mechanism,queries}，POST /runs/{id}/privacy-queries→{request,epsilon,result,budget,reused}。
export const ENTITY_KEYS=['sources','policies','runs','schedules','deliveries'];
