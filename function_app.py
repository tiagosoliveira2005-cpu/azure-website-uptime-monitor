from datetime import datetime
import azure.functions as func
from azure.data.tables import TableServiceClient
import time
import requests
import json
import re
import logging
import os

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

def normalize_url(url: str) -> str:
    
    # Remove espaços extras no início e no fim
    url = url.strip()
    
    # Verifica se começa com http:// ou https://
    if url.startswith(("http://", "https://")):
        return url
    else:
        return "https://" + url
    
def sanitize_partition_key(url: str) -> str:
    
    # Remove espaços extras no início e no fim
    url = url.strip()
    
    # Verifica se começa com http:// ou https://
    if url.startswith(("http://", "https://")):
        resultado = re.sub(r'^(http://|https://)', '', url)
        resultado = resultado.replace("/", "_")  # Replace slashes with underscores
        return resultado 
    else:
        url = url.replace("/", "_")  # Replace slashes with underscores
        return url
    
def is_valid_url(url):
    pattern = re.compile(
        r'^(https?:\/\/)'          # protocolo obrigatório (http ou https)
        r'([\w\-]+\.)+[a-zA-Z]{2,}' # domínio (ex: exemplo.com)
        r'(:\d+)?'                  # porta opcional (ex: :8080)
        r'(\/[^\s]*)?$'             # caminho opcional (ex: /pagina)
    )
    return re.match(pattern, url) is not None

def perform_check(url: str) -> dict:
    start = time.time()
    try:
        r = requests.get(url, timeout=15)  
    except requests.exceptions.RequestException as e:
        python_dict = {"status": "DOWN",
                       "web_status_code": None,
                       "response_time": round(time.time() - start, 2),
                       "error_motive": str(e)}
        logging.error(f"Error checking website {url}: {e}")
        return python_dict
    end = time.time()

    elapsed_time = round(end - start, 2)

    if 100<=r.status_code<200:
        status = "INFORMATIVE"
    elif 200<=r.status_code<400:
        status = "OPERATIONAL"
    elif 400<=r.status_code<600:
        status = "DOWN" 
    else:
        status = "UNKNOWN"    

    python_dict = {"status": status,
                   "web_status_code": r.status_code,
                   "response_time": elapsed_time,
                   "error_motive": None}
    logging.info(f"Website check result for {url}: {status} | {r.status_code} | {elapsed_time}s")
    return python_dict

@app.route(route="check_website")
def check_website(req: func.HttpRequest) -> func.HttpResponse:
    
    url = req.params.get('url')
    if not url:
        python_dict = {"status": "Error",
                       "web_status_code": None,
                       "response_time": "N/A",
                       "error_motive": "Missing 'url' parameter in the request."}
        return func.HttpResponse(body=json.dumps(python_dict), status_code=400, mimetype="application/json")
    
    url = normalize_url(url)

    if not is_valid_url(url):
        python_dict = {"status": "Error",
                       "web_status_code": None,
                       "response_time": "N/A",
                       "error_motive": "Invalid URL format. Ensure it includes a valid domain and path."}
        return func.HttpResponse(body=json.dumps(python_dict), status_code=400, mimetype="application/json")
    logging.info(f"Checking website: {url}")

    result = perform_check(url)
    return func.HttpResponse(body=json.dumps(result), status_code=200, mimetype="application/json")

@app.timer_trigger(schedule="0 */5 * * * *", arg_name="myTimer", run_on_startup=False,
              use_monitor=False) 
def monitor_websites(myTimer: func.TimerRequest) -> None:
    
    function_key = os.environ.get("WEBSITE_FUNCTION_KEY", "")
    base_url = os.environ.get("FUNCTION_APP_BASE_URL", "")
    url_with_params = f"{base_url}/api/check_website"

    monitored_urls = os.environ.get("MONITORED_URLS", "")
    urls = monitored_urls.split(",")
    
    for url in urls:
        stripped_url = url.strip()
        request_url = f"{url_with_params}?url={stripped_url}"
        try:
            response = requests.get(request_url, timeout=15, headers={"x-functions-key": function_key})
            if response.status_code == 200:
                logging.info(f"Successfully checked website {stripped_url}: {response.json()}")
                string = sanitize_partition_key(stripped_url)
                save_check_result(string, response.json())
            else:
                logging.warning(f"Failed to check website {stripped_url}: HTTP {response.status_code} - {response.text}") 
                string = sanitize_partition_key(stripped_url)
                save_check_result(string, {"status": "Error", "web_status_code": response.status_code, "response_time": "N/A", "error_motive": f"HTTP {response.status_code} - {response.text}"})
        except requests.exceptions.RequestException as e:
            logging.error(f"Error occurred while checking website {url}: {e}")


    logging.info('Python timer trigger function executed.')

def save_check_result(site: str, result: dict):
    connection_string = os.environ.get("STORAGE_CONNECTION_STRING", "")
    table_service = TableServiceClient.from_connection_string(conn_str=connection_string)
    table = table_service.create_table_if_not_exists(table_name="WebsiteChecks")
    entity = {
        "PartitionKey": site,
        "RowKey": datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S"),
        "Status": result["status"],
        "WebStatusCode": result["web_status_code"],
        "ResponseTime": result["response_time"],
        "ErrorMotive": result["error_motive"]
    }
    table.upsert_entity(entity)