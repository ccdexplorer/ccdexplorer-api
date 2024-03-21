from fastapi import Request


async def get_mongo_db(req: Request):
    return req.app.mongodb


async def get_mongo_motor(req: Request):
    return req.app.motormongo


async def get_grpcclient(req: Request):
    return req.app.grpcclient


async def get_tooter(req: Request):
    return req.app.tooter
