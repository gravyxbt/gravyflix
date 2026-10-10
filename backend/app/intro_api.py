from fastapi import APIRouter
from . import intros
router=APIRouter()

@router.get('/api/movies/{movie_id}/intro')
def intro(movie_id:int):
    from .main import get_movie
    return intros.available(get_movie(movie_id))
