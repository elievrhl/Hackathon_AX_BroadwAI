"""One-click bookmarks, independent of edition archives and optional collections."""

from fastapi import APIRouter, Query, Request

from broadwai.collections import AddArticle, call, repository

router = APIRouter(prefix="/v1/saved-articles")


@router.get("")
def saved_articles(request: Request, user_id: str = Query(min_length=1, max_length=100)):
    return repository(request).saved(user_id)


@router.put("/{article_id}")
def save_article(
    article_id: str,
    data: AddArticle,
    request: Request,
    user_id: str = Query(min_length=1, max_length=100),
):
    return call(lambda: repository(request).save(user_id, article_id, data.cover_id))


@router.delete("/{article_id}")
def unsave_article(
    article_id: str,
    request: Request,
    user_id: str = Query(min_length=1, max_length=100),
):
    return repository(request).unsave(user_id, article_id)
