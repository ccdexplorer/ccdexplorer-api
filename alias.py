import subprocess
from ccdexplorer_fundamentals.mongodb import (
    MongoDB,
    MongoMotor,
    Collections,
    CollectionsUtilities,
    MongoTokensImpactedAddress,
)
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.tooter import Tooter
from pymongo import ASCENDING, DESCENDING, ReplaceOne, DeleteOne
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import *
from ccdexplorer_fundamentals.cis import (
    MongoTypeLoggedEvent,
    mintEvent,
    burnEvent,
    transferEvent,
)

# from env import *
from rich import print
from rich.progress import track

grpcclient = GRPCClient()
tooter = Tooter()

mongodb = MongoDB(tooter)
motormongo = MongoMotor(tooter)


db_to_use = mongodb.utilities_db


aliases = []
net = "testnet"
account = "4NkwL9zPsZF6Y8VDztVtBv38fmgoY8GneDsGZ6zRpTZJgyX29E"
for counter in range(0, 5):
    args = [
        "concordium-client",
        "account",
        "show-alias",
        account,
        "--alias",
        str(counter),
    ]
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print(result.stdout.decode().split()[-1])
    d = {
        "_id": f"{counter}-{net}",
        "alias_id": counter,
        "alias": result.stdout.decode().split()[-1],
        "net": net,
    }
    _ = db_to_use["api_aliases"].bulk_write(
        [
            ReplaceOne(
                {"_id": f"{counter}-{net}"},
                replacement=d,
                upsert=True,
            )
        ]
    )
