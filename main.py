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
import random
import hashlib
from os.path import exists

server = "https://iaso.bluesquare.org"
forms_endpoint = server + "/api/forms/"
instances_endpoint = server + "/api/instances/"


class SilentUndefined(Undefined):
    def _fail_with_undefined_error(self, *args, **kwargs):
        return ""


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


def access_and_cache(url, use_cache=True):
    m = hashlib.sha256(url.encode("UTF-8")).hexdigest()
    path = "cache/%s" % m

    if exists(path):
        # print("using cache!")
        f = open(path, "rt")
        res = json.loads(f.read())
        f.close()
        return res

    r = requests.get(
        url,
        headers=headers,
    )

    f = open(path, "w")
    f.write(r.text)
    f.close()
    return r.json()


def get_as_info(as_id):
    # request AS data and the relevant submissions
    data = {}
    data["as"] = access_and_cache(
        "https://iaso.bluesquare.org/api/orgunits/%d/" % as_id
    )
    reference_instance_id = data["as"]["reference_instance_id"]

    data["forms"] = access_and_cache(
        "https://iaso.bluesquare.org/api/instances/?orgUnitId=%d&showDeleted=false"
        % reference_instance_id
    )

    # Handling fosas and their reference form
    ##########################################

    data["fosas"] = access_and_cache(
        "https://iaso.bluesquare.org/api/orgunits/?validation_status=VALID&orgUnitParentId=%d&onlyDirectChildren=true&limit=1000&order=name&page=1&orgUnitTypeId=207"
        % as_id
    )["orgunits"]
    fosa_dict = {}
    for i in data["fosas"]:
        fosa_dict[i.get("id")] = i

    fosa_leader_instance = None
    instances = access_and_cache(
        "https://iaso.bluesquare.org/api/instances/?orgUnitTypeId=207&form_ids=735&limit=200&order=-updated_at&page=1&showDeleted=false&orgUnitParentId=%d"
        % as_id
    )["instances"]
    for i in instances:
        file_content = i.get("file_content")
        f_dict = fosa_dict.get(i.get("org_unit").get("id"), {})
        f_dict[
            "donnees_fosa"
        ] = file_content  # adding the content of the form as a field in the dictionary representing the FOSA, so that I can use that later in templates
        if file_content.get("leader"):
            fosa_leader_instance = i

    data["fosa_leader_instance"] = fosa_leader_instance

    # Handling localites and their reference form (same pattern as for FOSA
    ##########################################

    data["localites"] = access_and_cache(
        "https://iaso.bluesquare.org/api/orgunits/?validation_status=VALID&orgUnitParentId=%d&onlyDirectChildren=true&limit=1000&order=name&page=1&orgUnitTypeId=211"
        % as_id
    )["orgunits"]

    localite_dict = {}
    for i in data["localites"]:
        localite_dict[i.get("id")] = i

    instances = access_and_cache(
        "https://iaso.bluesquare.org/api/instances/?orgUnitTypeId=211&form_ids=734&limit=200&order=-updated_at&page=1&showDeleted=false&orgUnitParentId=%d"
        % as_id
    )["instances"]
    for i in instances:
        file_content = i.get("file_content")
        l_dict = localite_dict.get(i.get("org_unit").get("id"), {})
        l_dict["microplan"] = file_content
        # print(json.dumps(file_content, indent=2))
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
        count_fosa=count_fosa,
        range_20=list(range(1, 20)),
    )

    # Write the rendered HTML to a file
    path = "generated/%d.html" % as_id
    with open(path, "w") as f:
        f.write(html)
    return path


if __name__ == "__main__":
    # as_ids = [1056335, 1056978, 1049730, 1051335, 1050055, 1053714, 1053203]
    from as_ids import as_ids

    random.shuffle(as_ids)
    as_ids = [1053203]
    # as_ids = [1056335, 1056978, 1049730, 1051335, 1050055, 1053714, 1053203]
    for as_id in as_ids:
        #try:
            data = get_as_info(as_id)
            print(as_id, data.get("as").get("name"))
            # create_map(data)
            path = write_html(data)
            HTML(path).write_pdf(
                "generated/%s-%d.pdf" % (data.get("as").get("name"), as_id)
            )
        #except:
        #    print("failed for as nr: ", as_id)
