from fastapi import APIRouter,Depends
from src.config.database import database
from src.controllers.auth import current
from src.schemas.requests import PrivacyQueryInput
from src.services import privacy as service
router=APIRouter()
@router.get('/runs/{id}/privacy')
def privacy_info(id:int,db=Depends(database),u=Depends(current)): return service.info(db,id)
@router.post('/runs/{id}/privacy-queries')
def privacy_query(id:int,b:PrivacyQueryInput,db=Depends(database),u=Depends(current)): return service.query(db,u,id,b)
