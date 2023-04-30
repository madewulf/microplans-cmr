from weasyprint import HTML
import getpass
import requests
import os
import json
from jinja2 import Environment, FileSystemLoader
from datetime import date
import locale

server = "https://iaso.bluesquare.org"
forms_endpoint = server + "/api/forms/"
instances_endpoint = server + "/api/instances/"


def get_headers():
    # Check if token exists in cache
    if os.path.exists("token_cache.txt"):
        with open("token_cache.txt", "r") as file:
            token = file.read().strip()
            if token:
                return {"Authorization": "Bearer %s" % token}

    # Get user credentials
    USERNAME = getpass.getpass("username")
    PASSWORD = getpass.getpass("password")

    # API setup

    creds = {"username": USERNAME, "password": PASSWORD}
    r = requests.post(server + "/api/token/", json=creds)
    token = r.json().get("access")

    # Cache the token
    with open("token_cache.txt", "w") as file:
        file.write(token)

    return {"Authorization": "Bearer %s" % token}


# get API token
headers = get_headers()


def get_as_info(as_id):
    # request form data
    data = {}
    r = requests.get(
        "https://iaso.bluesquare.org/api/forms/?fields=id,name,label_keys,period_type,org_unit_type_ids",
        headers=headers,
    )
    data["forms"] = r.json()
    r = requests.get(
        "https://iaso.bluesquare.org/api/orgunits/%d/" % as_id, headers=headers
    )
    data["as"] = r.json()
    reference_instance_id = data["as"]["reference_instance_id"]
    r = requests.get(
        "https://iaso.bluesquare.org/api/instances/?orgUnitId=%d&showDeleted=false"
        % reference_instance_id,
        headers=headers,
    )
    data["forms"] = r.json()
    r = requests.get(
        "https://iaso.bluesquare.org/api/orgunits/?validation_status=VALID&orgUnitParentId=%d&onlyDirectChildren=true&limit=1000&order=name&page=1&orgUnitTypeId=207"
        % as_id,
        headers=headers,
    )
    data["fosas"] = r.json()["orgunits"]
    r = requests.get(
        "https://iaso.bluesquare.org/api/orgunits/?validation_status=VALID&orgUnitParentId=%d&onlyDirectChildren=true&limit=1000&order=name&page=1&orgUnitTypeId=211"
        % as_id,
        headers=headers,
    )
    data["localites"] = r.json()["orgunits"]
    return data


def write_html(data):
    as_id = data.get("as").get("id")
    # Load the Jinja2 template from a separate file
    env = Environment(loader=FileSystemLoader("."))
    template = env.get_template("as_template.html")

    # Define the path to the image file
    image_path = "images/%d.png" % as_id

    # Render the template with the image path
    locale.setlocale(locale.LC_TIME, 'fr_FR')
    today = date.today()
    date_str = today.strftime('%A %d %B %Y')
    print(json.dumps(data.get("as"), indent=2))
    count_localite = len(data.get("localites"))
    count_fosa = len(data.get("fosas"))
    html = template.render(image_path=image_path, date_str=date_str, data=data, count_localite=count_localite,count_fosa=count_fosa )

    # Write the rendered HTML to a file
    path = "generated/%d.html" % as_id
    with open(path, "w") as f:
        f.write(html)
    return path


if __name__ == "__main__":
    as_id = 1051335 #1049730 #1050055 #1053714
    data = get_as_info(as_id)
    path = write_html(data)
    HTML(path).write_pdf("generated/%d.pdf" % as_id)
# See PyCharm help at https://www.jetbrains.com/help/pycharm/
