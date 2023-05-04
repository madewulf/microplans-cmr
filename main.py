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
import openpyxl
import shutil


from os.path import exists
from pypdf import PdfWriter

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


def access_and_cache(url, use_cache=False):
    m = hashlib.sha256(url.encode("UTF-8")).hexdigest()
    path = "cache/%s" % m

    if exists(path) and use_cache:
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
        % as_id
    )["instances"]

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

    # handling cold chain
    instances = access_and_cache(
        "https://iaso.bluesquare.org/api/instances/?orgUnitTypeId=207&form_ids=740&limit=20&order=org_unit__name&page=1&showDeleted=false&orgUnitParentId=%s"
        % as_id
    )["instances"]
    for i in instances:
        file_content = i.get("file_content")
        l_dict = fosa_dict.get(i.get("org_unit").get("id"), {})
        l_dict["cold_chain"] = file_content

    # handling personnel
    instances = access_and_cache(
        "https://iaso.bluesquare.org/api/instances/?orgUnitTypeId=207&form_ids=738&limit=20&order=org_unit__name&page=1&showDeleted=false&orgUnitParentId=%s"
        % as_id
    )["instances"]
    for i in instances:
        file_content = i.get("file_content")
        l_dict = fosa_dict.get(i.get("org_unit").get("id"), {})
        l_dict["personnel"] = file_content

    return data


def create_map(data):
    as_id = data.get("as").get("id")
    m = StaticMap(900, 600, padding_x=0, padding_y=0)
    try:
        coordinates = (
            data.get("as")
            .get("geo_json")
            .get("features")[0]
            .get("geometry")
            .get("coordinates")[0][0]
        )
        polygon = Polygon(coordinates, "#0000FF22", "#0066CC", True)
        m.add_polygon(polygon)
    except:
        pass
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


def append_end(path, end_path):
    merger = PdfWriter()

    for pdf in [path, "end.pdf"]:
        merger.append(pdf)

    merger.write(end_path)
    merger.close()
    return path


def process(as_id):
    data = get_as_info(as_id)
    #print(as_id, data.get("as").get("name"))
    create_map(data)
    path = write_html(data)
    pdf_path = "generated/%s-%d.pdf" % (data.get("as").get("name"), as_id)
    end_path = "generated/microplan-%s-%d.pdf" % (data.get("as").get("name"), as_id)
    HTML(path).write_pdf(pdf_path)
    append_end(pdf_path, end_path)
    return end_path


def fill_xls_with_form(sheet_name, columns, start_line, form_name, workbook, items):
    worksheet = workbook.get_sheet_by_name(sheet_name)
    i = 0
    for fosa in items:
        #print(fosa.get(form_name))
        for key in columns:
            cell = "%s%d" % (columns[key], start_line + i)
            value = fosa.get(key, None)
            if value is None:
                value = fosa.get(form_name, {}).get(key, None)

            #print(cell, key, value)
            try:
                try:
                    #print(value, type(value))
                    value = float(value)

                except:
                    pass
                worksheet[cell] = value
            except:
                pass
        i += 1


def create_excel(as_id):
    data = get_as_info(as_id)
    create_map(data)
    generated_path = "generated/excel/microplan-%s-%d.xlsx" % (
        data.get("as").get("name"),
        as_id,
    )
    workbook = openpyxl.load_workbook("Modele_microplan_AS.xlsx")
    worksheet = workbook.get_sheet_by_name("0_Couverture")
    image_path = "generated/images/%d.png" % as_id
    if os.path.exists(image_path):
        img = openpyxl.drawing.image.Image(image_path)
        img.anchor = 'A31'
        img.height = 600*1.7  # insert image height in pixels as float or int (e.g. 305.5)
        img.width = 900*1.7
        worksheet.add_image(img)

    worksheet["E17"] = data.get("as").get("parent").get("parent").get("name")
    worksheet["E18"] = data.get("as").get("parent").get("name")
    worksheet["E19"] = data.get("as").get("name")
    worksheet["E20"] = data.get("fosa_leader_instance").get("org_unit").get("name")
    worksheet["E21"] = data.get("fosa_leader_instance").get("file_content").get("responsable_fosa")
    worksheet["E22"] = data.get("fosa_leader_instance").get("file_content").get("tel_responsable_fosa")

    count_fosa = len(data.get("fosas"))
    worksheet["J24"] = count_fosa
    count_localite = len(data.get("localites"))
    worksheet["J26"] = count_localite

    #FOSAS
    columns = {
        "name": "B",
        "distance_fosa_ssd": "C",
        "statut_fosa": "D",
        "type_acces_ssd": "E",
        "fosa_vaccine": "F",
        "responsable_fosa": "G",
        "tel_responsable_fosa": "H",
        "id": "I"
    }
    fill_xls_with_form(
        "1_Liste fosa", columns, 4, "donnees_fosa", workbook, data.get("fosas")
    )

    #LOCALITES
    columns = {
        "name": "B",
        "localite_haute_tension": "F",
        "raison_haute_attention": "G",
        "population_denombre": "H",
        "population_polio_0_59": "L",
        "id": "R"
    }
    fill_xls_with_form(
        "2a_Liste localites (toutes)", columns, 5, "microplan", workbook, data.get("localites")
    )

    workbook.save(generated_path)
    return generated_path

if __name__ == "__main__":
    from as_ids import as_ids

    random.shuffle(as_ids)
    as_ids = [1056142]

    for as_id in as_ids:
        # try:
        # process(as_id)
        create_excel(as_id)
    # except:
    #   print("failed for as nr: ", as_id)

from flask import Flask
from flask import send_file
from flask import request

app = Flask(__name__)


@app.route("/generate/<int:as_id>")
def generate_microplan(as_id):
    as_id = int(as_id)
    pdf = process(as_id)

    return send_file(pdf)


@app.route("/generate_xls/<int:as_id>")
def generate_microplan_excel(as_id):
    as_id = int(as_id)
    excel = create_excel(as_id)

    return send_file(excel)

@app.route("/")
def index():
    env = Environment(loader=FileSystemLoader("."), undefined=SilentUndefined)
    template = env.get_template("index.html")
    html = template.render()
    return html


@app.route("/treesearch/")  # proxying treesearch
def treesearch():
    path = (
        "https://iaso.bluesquare.org/api/orgunits/treesearch/?%s"
        % request.query_string.decode("utf-8")
    )

    r = requests.get(
        path,
        headers=headers,
    )

    return r.json()
