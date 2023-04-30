from weasyprint import HTML
import getpass
import requests
import os
import json
from jinja2 import Environment, FileSystemLoader
from datetime import date
import locale
from staticmap import StaticMap, CircleMarker, StaticMap, Line, Polygon
from haversine import haversine
from jinja2 import Undefined, Template


server = "https://iaso.bluesquare.org"
forms_endpoint = server + "/api/forms/"
instances_endpoint = server + "/api/instances/"


class SilentUndefined(Undefined):
    def _fail_with_undefined_error(self, *args, **kwargs):
        return ''


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
    as_dict = {}
    for i in data["fosas"]:
        file_content =  i.get("file_content")
        print(file_content)
        as_dict[i.get("id")] = i
    print("as_dict", as_dict)

    r = requests.get(
        "https://iaso.bluesquare.org/api/orgunits/?validation_status=VALID&orgUnitParentId=%d&onlyDirectChildren=true&limit=1000&order=name&page=1&orgUnitTypeId=211"
        % as_id,
        headers=headers,
    )
    data["localites"] = r.json()["orgunits"]
    r = requests.get(
        "https://iaso.bluesquare.org/api/instances/?orgUnitTypeId=207&form_ids=735&limit=200&order=-updated_at&page=1&showDeleted=false&orgUnitParentId=%d"
        % as_id,
        headers=headers,
    )

    fosa_leader_instance = None
    for i in r.json()["instances"]:
        file_content =  i.get("file_content")
        area_dict = as_dict[i.get("org_unit").get("id")]
        area_dict["donnees_fosa"] = file_content
        if file_content.get("leader"):
            fosa_leader_instance = i

    data["donnes_fosa"] = as_dict

    data["fosa_leader_instance"] = fosa_leader_instance
    return data


def create_map(data):
    as_id = data.get("as").get("id")
    m = StaticMap(1400, 1200, padding_x=-200, padding_y=-200)
    coordinates = (
        data.get("as")
        .get("geo_json")
        .get("features")[0]
        .get("geometry")
        .get("coordinates")[0][0]
    )
    polygon = Polygon(coordinates, "#0000FF22", "#0066CC", True)
    m.add_polygon(polygon)

    for fosa in data.get("fosas"):
        latitude = fosa.get("latitude")
        longitude = fosa.get("longitude")

        if latitude and longitude:
            marker = CircleMarker(
                (longitude, latitude), "#E53834", 12, name=fosa.get("name")
            )
            m.add_marker(marker)

    for localite in data.get("localites"):
        latitude = localite.get("latitude")
        longitude = localite.get("longitude")

        if latitude and longitude:
            marker = CircleMarker(
                (longitude, latitude), "#00897B", 12, name=localite.get("name")
            )
            m.add_marker(marker)

    image = m.render()
    image.save("generated/images/%d.png" % as_id)


def write_html(data):
    area = data.get("as")
    as_id = area.get("id")
    # Load the Jinja2 template from a separate file
    env = Environment(loader=FileSystemLoader("."), undefined=SilentUndefined)
    template = env.get_template("as_template.html")
    # Define the path to the image file
    image_path = "images/%d.png" % as_id

    # Render the template with the image path
    locale.setlocale(locale.LC_TIME, "fr_FR")
    today = date.today()
    date_str = today.strftime("%A %d %B %Y")
    # print(json.dumps(data.get("as"), indent=2))
    count_localite = len(data.get("localites"))
    count_fosa = len(data.get("fosas"))

    # latitude_area, longitude_area = area.get("latitude"), area.get("longitude")
    # district = area.get("parent")
    # latitude_district, longitude_district = district.get("latitude"), district.get("longitude")
    # distance_district = haversine(latitude_area, longitude_area, latitude_district, longitude_district)
    # print("distance_district", distance_district)

    html = template.render(
        image_path=image_path,
        date_str=date_str,
        data=data,
        count_localite=count_localite,
        count_fosa=count_fosa
    )

    # Write the rendered HTML to a file
    path = "generated/%d.html" % as_id
    with open(path, "w") as f:
        f.write(html)
    return path


if __name__ == "__main__":
    as_ids = [1056335, 1056978, 1049730, 1051335, 1050055, 1053714]
    for as_id in as_ids:
        data = get_as_info(as_id)
        create_map(data)
        path = write_html(data)
        HTML(path).write_pdf("generated/%d.pdf" % as_id)


# See PyCharm help at https://www.jetbrains.com/help/pycharm/
