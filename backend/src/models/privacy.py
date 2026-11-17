from sqlalchemy import Column,Integer,String,JSON,Text,Float
from src.config.database import Base
class PrivacyBudget(Base):
 __tablename__='privacy_budgets'
 id=Column(Integer,primary_key=True); run_id=Column(Integer,unique=True); total=Column(Float); spent=Column(Float,default=0); created=Column(Float)
class PrivacyQuery(Base):
 __tablename__='privacy_queries'
 id=Column(Integer,primary_key=True); run_id=Column(Integer); dedupe_key=Column(String(64),unique=True); actor=Column(String(120)); request=Column(JSON); epsilon=Column(Float); status=Column(String(20)); reason=Column(Text,default=''); result=Column(JSON); created=Column(Float)
