import os
import os.path
import logging
import tempfile
from typing import IO
import zipfile
from datetime import datetime, timedelta, date, timezone
import json
import base64
import bizdays
import pytz
import requests

class SimpleDownloader:
    def __init__(self, **kwargs):
        self.verify_ssl = kwargs.get("verify_ssl", True)
        self._url = kwargs["url"]
        self.response = None

    @property
    def url(self) -> str:
        return self._url

    @property
    def status_code(self) -> int:
        return self.response.status_code

    def download(self) -> IO | None:
        res = requests.get(self.url, verify=self.verify_ssl)
        self.response = res
        
        msg = "status_code = {} url = {}".format(res.status_code, self.url)
        logg = logging.warn if res.status_code != 200 else logging.info
        logg(msg)
        
        if res.status_code != 200:
            return None
        
        temp = tempfile.TemporaryFile()
        temp.write(res.content)
        temp.seek(0)
        return temp


class DatetimeDownloader(SimpleDownloader):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.refdate = kwargs["refdate"]

    @property
    def url(self) -> str:
        return self.refdate.strftime(self._url)


def get_date(dt):
    return dt.date() if isinstance(dt, datetime) else dt


def get_month(dt, monthdelta):
    first = date(dt.year, dt.month, 1)
    delta = 0
    while delta > monthdelta:
        first += timedelta(-1)
        dt = first
        first = date(dt.year, dt.month, 1)
        delta -= 1
    return first


class StaticFileDownloader(SimpleDownloader):
    SP_TZ = pytz.timezone("America/Sao_Paulo")

    def get_url(self, refdate):
        return self.attrs["url"]

    def get_fname2(self, refdate):
        if self.attrs.get("ext"):
            ext = ".{}".format(self.attrs["ext"])
        else:
            _, ext = os.path.splitext(self._url)
        fname = "{}{}".format(refdate.strftime("%Y-%m-%d"), ext)
        return fname

    def download(self, refdate=None):
        self._url = self.get_url(refdate)
        verify_ssl = self.attrs.get("verify_ssl", True)
        _, tfile, status_code, res = download_url(self._url, verify_ssl=verify_ssl)
        refdate = datetime.strptime(
            res.headers["last-modified"], "%a, %d %b %Y %H:%M:%S %Z"
        )
        refdate = pytz.UTC.localize(refdate).astimezone(self.SP_TZ)
        if status_code != 200:
            return None, None, status_code, refdate

        fname = self.get_fname2(refdate)
        f_fname = self.get_fname(fname, refdate)
        return f_fname, tfile, status_code, refdate


class StaticZipFileDownloader(SimpleDownloader):
    SP_TZ = pytz.timezone("America/Sao_Paulo")

    def get_url(self, refdate):
        return self.attrs["url"]

    def get_fname2(self, refdate):
        if self.attrs.get("ext"):
            ext = ".{}".format(self.attrs["ext"])
        else:
            _, ext = os.path.splitext(self._url)
        fname = "{}{}".format(refdate.strftime("%Y-%m-%d"), ext)
        return fname

    def download(self, refdate=None):
        self._url = self.get_url(refdate)
        verify_ssl = self.attrs.get("verify_ssl", True)
        _, tfile, status_code, res = download_url(self._url, verify_ssl=verify_ssl)
        refdate = datetime.strptime(
            res.headers["last-modified"], "%a, %d %b %Y %H:%M:%S %Z"
        )
        refdate = pytz.UTC.localize(refdate).astimezone(self.SP_TZ)
        if status_code != 200:
            return None, None, status_code, refdate

        zf = zipfile.ZipFile(tfile)
        nl = zf.namelist()
        if len(nl) == 0:
            logging.error("zip file is empty url = {}".format(self._url))
            return None, None, 204
        name = nl[0]
        content = zf.read(name)  # bytes
        zf.close()
        tfile.close()
        temp = tempfile.TemporaryFile()
        temp.write(content)
        temp.seek(0)

        fname = self.get_fname2(refdate)
        f_fname = self.get_fname(fname, refdate)
        return f_fname, temp, status_code, refdate


class FormatDateStaticFileDownloader(StaticFileDownloader):
    def get_url(self, refdate):
        refdate = refdate or self.now + timedelta(self.attrs.get("timedelta", 0))
        logging.debug("REFDATE %s", refdate)
        logging.debug("SELF NOW %s", self.now)
        logging.debug("TIMEDELTA %s", self.attrs.get("timedelta", 0))
        return refdate.strftime(self.attrs["url"])


class FundosInfDiarioDownloader(StaticZipFileDownloader):
    def get_refmonth(self):
        return get_month(self.now, self.attrs["month_reference"])

    def get_url(self, refdate):
        refmonth = self.get_refmonth()
        return refmonth.strftime(self.attrs["url"])

    def get_fname2(self, refdate):
        if self.attrs.get("ext"):
            ext = ".{}".format(self.attrs["ext"])
        else:
            _, ext = os.path.splitext(self._url)
        refmonth = self.get_refmonth()
        fname = "{}/{}{}".format(
            refmonth.strftime("%Y-%m"), refdate.strftime("%Y-%m-%d"), ext
        )
        return fname


class PreparedURLDownloader(SimpleDownloader):
    def download(self, refdate=None):
        url = self.attrs["url"]
        refdate = refdate or self.now + timedelta(self.attrs.get("timedelta", 0))
        params = {}
        for param in self.attrs["parameters"]:
            param_value = self.attrs["parameters"][param]
            if isinstance(param_value, dict):
                if param_value["type"] == "datetime":
                    params[param] = refdate.strftime(param_value["value"])
            else:
                params[param] = param_value

        self._url = url.format(**params)
        fname, temp_file, status_code = self._download_unzip_historical_data(self._url)
        if status_code != 200:
            return None, None, status_code, refdate
        f_fname = self.get_fname(fname, refdate)
        return f_fname, temp_file, status_code, refdate

    def _download_unzip_historical_data(self, url):
        verify_ssl = self.attrs.get("verify_ssl", True)
        _, temp, status_code, res = download_url(url, verify_ssl=verify_ssl)
        if status_code != 200:
            return None, None, status_code
        zf = zipfile.ZipFile(temp)
        nl = zf.namelist()
        if len(nl) == 0:
            logging.error("zip file is empty url = {}".format(url))
            return None, None, 204
        name = nl[0]
        content = zf.read(name)  # bytes
        zf.close()
        temp.close()
        temp = tempfile.TemporaryFile()
        temp.write(content)
        temp.seek(0)
        return name, temp, status_code


class B3FilesURLDownloader(SimpleDownloader):
    calendar = bizdays.Calendar.load("ANBIMA")

    def download(self, refdate=None):
        filename = self.attrs.get("filename")
        refdate = refdate or self.get_refdate()
        logging.info("refdate %s", refdate)
        date = refdate.strftime("%Y-%m-%d")
        url = f"https://arquivos.b3.com.br/api/download/requestname?fileName={filename}&date={date}&recaptchaToken="
        res = requests.get(url)
        msg = "status_code = {} url = {}".format(res.status_code, url)
        logg = logging.warn if res.status_code != 200 else logging.info
        logg(msg)
        if res.status_code != 200:
            return None, None, res.status_code, refdate
        ret = res.json()
        url = f'https://arquivos.b3.com.br/api/download/?token={ret["token"]}'
        verify_ssl = self.attrs.get("verify_ssl", True)
        fname, temp_file, status_code, res = download_url(url, verify_ssl=verify_ssl)
        if res.status_code != 200:
            return None, None, res.status_code, refdate
        f_fname = self.get_fname(fname, refdate)
        logging.info(
            "Returned from download %s %s %s %s",
            f_fname,
            temp_file,
            status_code,
            refdate,
        )
        return f_fname, temp_file, status_code, refdate

    def get_refdate(self):
        offset = self.attrs.get("offset", 0)
        refdate = self.calendar.offset(self.now, offset)
        refdate = datetime(refdate.year, refdate.month, refdate.day)
        refdate = pytz.timezone("America/Sao_Paulo").localize(refdate)
        return refdate


class B3StockIndexInfoDownloader(SimpleDownloader):
    calendar = bizdays.Calendar.load("ANBIMA")

    def download(self, refdate=None):
        params = json.dumps({"pageNumber": 1, "pageSize": 9999})
        params_enc = base64.encodebytes(bytes(params, "utf8")).decode("utf8").strip()
        url = f"https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetStockIndex/{params_enc}"
        verify_ssl = self.attrs.get("verify_ssl", True)
        fname, temp_file, status_code, res = download_url(url, verify_ssl=verify_ssl)
        if res.status_code != 200:
            return None, None, res.status_code, refdate
        f_fname = self.get_fname(None, self.now)
        logging.info(
            "Returned from download %s %s %s %s",
            f_fname,
            temp_file,
            status_code,
            refdate,
        )
        return f_fname, temp_file, status_code, refdate


class VnaAnbimaURLDownloader(SimpleDownloader):
    calendar = bizdays.Calendar.load("ANBIMA")

    def download(self, refdate=None):
        refdate = refdate or self.get_refdate()
        logging.info("refdate %s", refdate)
        url = "https://www.anbima.com.br/informacoes/vna/vna.asp"
        body = {
            "Data": refdate.strftime("%d%m%Y"),
            "escolha": "1",
            "Idioma": "PT",
            "saida": "txt",
            "Dt_Ref_Ver": refdate.strftime("%Y%m%d"),
            "Inicio": refdate.strftime("%d/%m/%Y"),
        }
        res = requests.post(url, params=body)
        msg = "status_code = {} url = {}".format(res.status_code, url)
        logg = logging.warn if res.status_code != 200 else logging.info
        logg(msg)
        if res.status_code != 200:
            return None, None, res.status_code, refdate
        status_code = res.status_code
        temp_file = tempfile.TemporaryFile()
        temp_file.write(res.content)
        temp_file.seek(0)
        f_fname = self.get_fname(None, refdate)
        logging.info(
            "Returned from download %s %s %s %s",
            f_fname,
            temp_file,
            status_code,
            refdate,
        )
        return f_fname, temp_file, status_code, refdate

    def get_refdate(self):
        offset = self.attrs.get("offset", 0)
        refdate = self.calendar.offset(self.now, offset)
        refdate = datetime(refdate.year, refdate.month, refdate.day)
        refdate = pytz.timezone("America/Sao_Paulo").localize(refdate)
        return refdate


def download_by_config(config_data, save_func, refdate=None):
    logging.info("content size = %d", len(config_data))
    config = json.loads(config_data)
    logging.info("content = %s", config)
    downloader = downloader_factory(**config)
    download_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f%z")
    logging.info("Download weekdays %s", config.get("download_weekdays"))
    if config.get("download_weekdays") and downloader.now.weekday() not in config.get(
        "download_weekdays"
    ):
        logging.info(
            "Not a date to download. Weekday %s Download Weekdays %s",
            downloader.now.weekday(),
            config.get("download_weekdays"),
        )
        msg = "Not a date to download. Weekday {} Download Weekdays {}".format(
            downloader.now.weekday(), config.get("download_weekdays")
        )
        return {
            "message": msg,
            "download_status": -1,
            "status": -1,
            "refdate": None,
            "filename": None,
            "bucket": config["output_bucket"],
            "name": config["name"],
            "time": download_time,
        }
    try:
        fname, tfile, status_code, refdate = downloader.download(refdate=refdate)
        logging.info("Download time (UTC) %s", download_time)
        logging.info("Refdate %s", refdate)
        if status_code == 200:
            save_func(config, fname, tfile)
            msg = "File saved"
            status = 0
        else:
            msg = "File not saved"
            status = 1
        return {
            "message": msg,
            "download_status": status_code,
            "status": status,
            "refdate": refdate and refdate.strftime("%Y-%m-%dT%H:%M:%S.%f%z"),
            "filename": fname,
            "bucket": config["output_bucket"],
            "name": config["name"],
            "time": download_time,
        }
    except Exception as ex:
        logging.error(str(ex))
        return {
            "message": str(ex),
            "download_status": -1,
            "status": 2,
            "refdate": None,
            "filename": None,
            "bucket": config["output_bucket"],
            "name": config["name"],
            "time": download_time,
        }


def save_file_to_temp_folder(attrs, fname, tfile):
    fname = "/tmp/{}".format(fname)
    logging.info("saving file %s", fname)
    os.makedirs(os.path.dirname(fname), exist_ok=True)
    with open(fname, "wb") as f:
        f.write(tfile.read())


