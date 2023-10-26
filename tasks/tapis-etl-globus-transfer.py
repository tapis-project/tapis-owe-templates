#-------- Workflow Context import: DO NOT REMOVE ----------------
from owe_python_sdk.runtime import execution_context as ctx
#-------- Workflow Context import: DO NOT REMOVE ----------------

import os, json, time

import requests

from tapipy.tapis import Tapis

from tasks.utils import ETLManifestModel


tapis_base_url = ctx.get_input("TAPIS_BASE_URL")
globus_proxy_base_url = os.path.join(tapis_base_url, "v3/globus-proxy/")
transfer_data = ctx.get_input("TRANSFER_DATA")
destination_endpoint_id = ctx.get_input("DESTINATION_ENDPOINT_ID")
source_endpoint_id = ctx.get_input("SOURCE_ENDPOINT_ID")
globus_client_id = ctx.get_input("GLOBUS_CLIENT_ID")
globus_access_token = ctx.get_input("GLOBUS_ACCESS_TOKEN")
globus_refresh_token = ctx.get_input("GLOBUS_REFRESH_TOKEN")

try:
    # Instantiate a Tapis client
    client = Tapis(
        base_url=tapis_base_url,
        jwt=ctx.get_input("TAPIS_JWT")
    )
except Exception as e:
    ctx.stderr(1, f"Error instantiating Tapis client: {e}")

try:
    tranfer_data = json.loads(transfer_data)
    path_to_manifest = transfer_data.get("path_to_manifest")
    local_system_id = transfer_data.get("system_id")
    manifest = ETLManifestModel(
        **json.loads(
            client.files.getContents(
                systemId=local_system_id,
                path=path_to_manifest
            )
        )
    )

    local_system = client.systems.getSystem(systemId=local_system_id)

    files_to_transfer = []
    for file in manifest.files:
        path = file.get("path").replace(f"tapis://{local_system}/", "")
        files_to_transfer.append(os.path.join(local_system.rootDir, path))

except Exception as e:
    ctx.stderr(1, f"Error fetching contents of manifest file '{path_to_manifest}': {e}")

try:
    # Create transfer task
    response = requests.post(
        url=os.path.join(globus_proxy_base_url, "transfers", globus_client_id),
        data={
            "source_endpoint": source_endpoint_id,
            "destination_endpoint": destination_endpoint_id,
            "transfer_items": [
                {
                    "source_path": path,
                    "destination_path": "", # TODO Allow user to provide dir, then we say where data goes
                    "recursive": False # TODO reconsider. Do we want to allow dirs?
                } for path in files_to_transfer
            ]
        }
    )
except Exception as e:
    ctx.stderr(f"Failed to create transfer task: {e}")

try:
    globus_transfer_task = response.result 
    max_retries = ctx.get_input("MAX_RETRIES", default=5)
    
    for i in range(max_retries): 
        globus_transfer_status = None
        num_retries = num_retries + 1
        response = requests.get(
            url = os.path.join(globus_proxy_base_url, 'transfers', globus_client_id, globus_transfer_task.task_id)
        )
        globus_transfer_status = response.status
        if globus_transfer_status == "SUCCEEDED":
            ctx.stdout(0, "Globus transfer completed successfully")
        elif globus_transfer_status == "FAILED" or globus_transfer_status == "INACTIVE":
            raise Exception("Globus transfer failed")
        else: # status is active, meaning the transfer is still happening
            time.sleep(5)
except Exception as e:
    ctx.stderr(1, e)