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
from jinja2 import Environment, FileSystemLoader
from jinja2.ext import i18n

from jinja2 import Environment, FileSystemLoader
from jinja2.ext import i18n
from babel.support import Translations

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

        if file_content.get("leader") == "1":
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
    try:
        image = m.render()
        image.save("generated/images/%d.png" % as_id)
    except Exception as e:  # it happens that there is nothing to draw and then it launches an exception
        print("Exception while generating the map", e)
        pass


def get_translations(lang):
    return Translations.load("translations", [lang])


def write_html(data, lang="fr"):
    area = data.get("as")
    as_id = area.get("id")
    # Load the Jinja2 template from a separate file
    env = Environment(
        loader=FileSystemLoader("."), extensions=[i18n], undefined=SilentUndefined
    )

    # Example of rendering a template with French translations
    translations = get_translations(lang)
    env.install_gettext_translations(translations)

    # env.install_gettext_translations()

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


def append_end(path, end_path, lang="fr"):
    merger = PdfWriter()

    if lang == "fr":
        end = "end.pdf"
    else:
        end = "end_EN.pdf"
    for pdf in [path, end]:
        merger.append(pdf)

    merger.write(end_path)
    merger.close()
    return path


def process(as_id, lang="fr"):
    data = get_as_info(as_id)
    # print(as_id, data.get("as").get("name"))
    create_map(data)
    path = write_html(data, lang)
    pdf_path = "generated/%s-%d.pdf" % (data.get("as").get("name"), as_id)
    end_path = "generated/microplan-%s-%d.pdf" % (data.get("as").get("name"), as_id)
    HTML(path).write_pdf(pdf_path)
    append_end(pdf_path, end_path)
    return end_path


def fill_xls_with_form(columns, start_line, form_name, worksheet, items):

    i = 0
    for item in items:

        # print(fosa.get(form_name))
        for key in columns:
            cell = "%s%d" % (columns[key], start_line + i)
            value = item.get(key, None)
            if value is None:
                value = item.get(form_name, {}).get(key, None)

            # print(cell, key, value)
            try:
                try:
                    # print(value, type(value))
                    value = float(value)

                except:
                    pass
                worksheet[cell] = value
            except:
                pass
        i += 1


def get_worksheet(workbook, french, english, lang="fr"):
    if lang == "fr":
        worksheet = workbook.get_sheet_by_name(french)
    else:
        worksheet = workbook.get_sheet_by_name(english)
    return worksheet


def create_excel(as_id, lang):
    data = get_as_info(as_id)
    create_map(data)
    print(data.get("as").get("name"))
    generated_path = "generated/excel/microplan-%s-%d.xlsx" % (
        data.get("as").get("name"),
        as_id,
    )
    if lang == "fr":
        workbook = openpyxl.load_workbook("Modele_microplan_AS.xlsx")
    else:
        workbook = openpyxl.load_workbook("Modele_microplan_AS_EN.xlsx")

    worksheet = get_worksheet(workbook, "0_Couverture", "0_Cover", lang)
    image_path = "generated/images/%d.png" % as_id
    if os.path.exists(image_path):
        img = openpyxl.drawing.image.Image(image_path)
        img.anchor = "A31"
        img.height = (
            600 * 1.7
        )  # insert image height in pixels as float or int (e.g. 305.5)
        img.width = 900 * 1.7
        worksheet.add_image(img)

    worksheet["E17"] = data.get("as").get("parent").get("parent").get("name")
    worksheet["E18"] = data.get("as").get("parent").get("name")
    worksheet["E19"] = data.get("as").get("name")
    if data.get("fosa_leader_instance", {}):
        worksheet["E20"] = (
            data.get("fosa_leader_instance", {}).get("org_unit", {}).get("name", "")
        )
        worksheet["E21"] = (
            data.get("fosa_leader_instance", {})
            .get("file_content", {})
            .get("responsable_fosa", "")
        )
        worksheet["E22"] = (
            data.get("fosa_leader_instance", {})
            .get("file_content", {})
            .get("tel_responsable_fosa", "")
        )
        worksheet["J28"] = (
            data.get("fosa_leader_instance", {})
            .get("file_content", {})
            .get("distance_fosa_ssd", 0)
        )
    count_fosa = len(data.get("fosas"))
    worksheet["J24"] = count_fosa
    count_localite = len(data.get("localites"))
    worksheet["J26"] = count_localite

    # FOSAS
    columns = {
        "name": "B",
        "distance_fosa_ssd": "C",
        "distance_fosa_pilote": "D",
        "statut_fosa": "E",
        "type_acces_ssd": "F",
        "fosa_vaccine": "G",
        "responsable_fosa": "H",
        "tel_responsable_fosa": "I",
        "id": "J",
    }
    worksheet = get_worksheet(workbook, "1_Liste fosa", "1_Health facilities list", lang)
    fill_xls_with_form(
        columns, 4, "donnees_fosa", worksheet, data.get("fosas")
    )

    # LOCALITES
    for localite in data.get("localites"):

        marches = ""

        for marche in localite.get("microplan", {}).get("marche_localite", ""):
            marches = marches + " " + marche.get("nom_marche", "") + "\n"
        localite["marches"] = marches

        ecoles = ""

        for ecole in localite.get("microplan", {}).get("ecole_primaire_publique", ""):
            ecoles = (
                ecoles
                + " "
                + ecole.get("nom_ecole_primaire_publique", "")
                + " - "
                + ecole.get("contact_ecole_primaire_publique", "")
                + " - "
                + ecole.get("responsible_ecole_primaire_publique", "")
                + "\n"
            )
        for ecole in localite.get("microplan", {}).get("ecole_maternel_publique", ""):
            ecoles = (
                ecoles
                + " "
                + ecole.get("nom_ecole_maternel_publique", "")
                + " - "
                + ecole.get("contact_ecole_maternel_publique", "")
                + " - "
                + ecole.get("responsible_ecole_maternel_publique", "")
                + "\n"
            )
        for ecole in localite.get("microplan", {}).get("ecole_primaire_privee", ""):
            ecoles = (
                ecoles
                + " "
                + ecole.get("nom_ecole_primaire_privee", "")
                + " - "
                + ecole.get("contact_ecole_primaire_privee", "")
                + " - "
                + ecole.get("responsible_ecole_primaire_privee", "")
                + "\n"
            )
        for ecole in localite.get("microplan", {}).get("ecole_maternel_privee", ""):
            ecoles = (
                ecoles
                + " "
                + ecole.get("nom_ecole_maternel_privee", "")
                + " - "
                + ecole.get("contact_ecole_maternel_privee", "")
                + " - "
                + ecole.get("responsible_ecole_maternel_privee", "")
                + "\n"
            )
        for ecole in localite.get("microplan", {}).get("ecole_primaire_cor", ""):
            ecoles = (
                ecoles
                + " "
                + ecole.get("nom_ecole_primaire_cor", "")
                + " - "
                + ecole.get("contact_ecole_primaire_cor", "")
                + " - "
                + ecole.get("responsible_ecole_primaire_cor", "")
                + "\n"
            )

        for ecole in localite.get("microplan", {}).get("creche_liste", ""):
            ecoles = (
                ecoles
                + " "
                + ecole.get("nom_creche", "")
                + " - "
                + ecole.get("contact_creche", "")
                + " - "
                + ecole.get("responsible_creche", "")
                + "\n"
            )
        for ecole in localite.get("microplan", {}).get("orphelinat_liste", ""):
            ecoles = (
                ecoles
                + " "
                + ecole.get("nom_orphelinat", "")
                + " - "
                + ecole.get("contact_orphelinat", "")
                + " - "
                + ecole.get("responsible_orphelinat", "")
                + "\n"
            )

        localite["ecoles"] = ecoles

        eglises = ""
        for eglise in localite.get("microplan", {}).get("liste_privee", ""):
            eglises = (
                eglises
                + " "
                + eglise.get("nom_eglise", "")
                + " - "
                + eglise.get("telephone_eglise", "")
                + "\n"
            )
        for mosquee in localite.get("microplan", {}).get("liste_mosquee", ""):
            eglises = (
                eglises
                + " "
                + mosquee.get("nom_mosquee", "")
                + " - "
                + mosquee.get("telephone_mosquee", "")
                + "\n"
            )
        localite["eglises"] = eglises

        passages = ""
        for passage in localite.get("microplan", {}).get("passage", ""):
            passages = passages + " " + passage.get("point_passage", "") + "\n"

        localite["passages"] = localite["eglises"] = eglises

    columns = {
        "name": "B",
        "localite_haute_tension": "F",
        "raison_haute_attention": "G",
        "population_denombre": "H",
        "population_polio_0_59": "N",
        "marches": "O",
        "ecoles": "P",
        "eglises": "Q",
        "passages": "R",
        "id": "T",
    }

    worksheet = get_worksheet(workbook, "2a_Liste localites (toutes)", "2a_Listof localities (all)", lang)
    fill_xls_with_form(
        columns,
        5,
        "microplan",
        worksheet,
        data.get("localites"),
    )

    columns = {
        "type_organisation": "A",
        "siege": "B",
        "responsible": "C",
        "telephone": "D",
    }

    obc_form = [f for f in data.get("forms") if f.get("form_name") == "MICROPLAN - OBC"]
    worksheet = get_worksheet(workbook, "4_Acteurs communication", "4_Communication actors", lang)
    fill_xls_with_form(
        columns,
        4,
        "file_content",
        worksheet,
        obc_form,
    )

    columns = {
        "fosa_name": "A",
        "nom_personnel": "B",
        "grade_personnel": "C",
        "tel_personnel": "D",
    }

    personnels = []
    for fosa in data.get("fosas"):

        for personnel in fosa.get("personnel", {}).get("personnel_fosa", {}):
            personnel["fosa_name"] = fosa.get("name")
            personnels.append(personnel)

    worksheet = get_worksheet(workbook, "6. Ressources humaines_disponib", "6. Available human resource ", lang)

    fill_xls_with_form(
        columns, 4, "personnel_fosa", worksheet, personnels
    )

    for fosa in data.get("fosas"):
        fosa["nbre_accumulateur_glacière"] = fosa.get("cold_chain",{}).get("nbre_accumulateur_glaciere", 0) + fosa.get("cold_chain",{}).get("nbre_accumulateur_pv3", 0)

    columns = {
        "qte_ecdf": "H",
        "qte_glaciere": "I",
        "qte_pv": "J",
        "nbre_accumulateur_glacière": "K",
        "nbre_accumulateur_pv": "L",
    }
    worksheet = get_worksheet(workbook, "7a.Chaine de Froid ", "7a.Cold chain ", lang )
    fill_xls_with_form(
         columns, 5, "cold_chain", worksheet, data.get("fosas")
    )

    workbook.save(generated_path)
    return generated_path


if __name__ == "__main__":
    from as_ids import as_ids

    random.shuffle(as_ids)
    as_ids = [1057811]

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
    lang = request.args.get("lang", "fr")
    as_id = int(as_id)
    pdf = process(as_id, lang)

    return send_file(pdf)


@app.route("/generate_xls/<int:as_id>")
def generate_microplan_excel(as_id):
    lang = request.args.get("lang", "fr")
    as_id = int(as_id)
    excel = create_excel(as_id, lang)

    return send_file(excel)


@app.route("/microplan_district")
def microplan_district():
    lang = request.args.get("lang", "fr")
    if lang == "fr":
        path = "Modele_Microplan_District_RR_2023.xlsx"
    else:
        path = "Modele_Microplan_District_RR_2023_EN.xlsx"
    return send_file(path)


@app.route("/")
def index():
    lang = request.args.get("lang", "fr")
    env = Environment(
        loader=FileSystemLoader("."), extensions=[i18n], undefined=SilentUndefined
    )
    translations = get_translations(lang)
    env.install_gettext_translations(translations)
    template = env.get_template("index.html")
    html = template.render({"lang": lang})
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
