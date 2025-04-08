import logging
import requests
import yaml

from bs4 import BeautifulSoup as bs
from datetime import date
from string import Template
from typing import List, Optional

logger = logging.getLogger("nne")


class Config:
    user: str
    nation: str
    password: str
    region: str
    delegate: Optional[str]
    test: bool
    title: Template
    template_path: str
    log_level: str

    def __init__(self, path: str):
        with open(path, "r") as in_file:
            data = yaml.safe_load(in_file)

        self.user = data["user"]
        self.nation = data["nation"]
        self.password = data["password"]
        self.region = data["region"]
        self.delegate = data.get("delegate")
        self.test = data["test"]
        self.title = Template(data["title"])
        self.template_path = data["template_path"]

        log_level = data.get("log_level")
        if log_level and log_level.upper() in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            self.log_level = log_level.upper()
        else:
            self.log_level = "INFO"

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console = logging.StreamHandler()
        console.setFormatter(formatter)

        logger = logging.getLogger("nne")
        logger.setLevel(self.log_level)
        logger.addHandler(console)

    def __repr__(self):
        return f"Config(user={self.user}, region={self.region}, delegate={self.delegate}, test={self.test})"


def get_delegate(user: str, region: str):
    return (
        bs(
            requests.get(
                f"https://www.nationstates.net/cgi-bin/api.cgi?region={region}&q=delegate",
                headers={"User-Agent": user},
            ).text,
            "xml",
        )
        .find("DELEGATE")
        .text
    )


def get_nnes(user: str, region: str, delegate: str) -> List[str]:
    wa_nations = (
        bs(
            requests.get(
                f"https://www.nationstates.net/cgi-bin/api.cgi?region={region}&q=wanations",
                headers={"User-Agent": user},
            ).text,
            "xml",
        )
        .find("UNNATIONS")
        .text.split(",")
    )

    del_endorsements = (
        bs(
            requests.get(
                f"https://www.nationstates.net/cgi-bin/api.cgi?nation={delegate}&q=endorsements",
                headers={"User-Agent": user},
            ).text,
            "xml",
        )
        .find("ENDORSEMENTS")
        .text.split(",")
    )

    return [nation for nation in wa_nations if nation not in del_endorsements]


def publish_nne(
    user: str,
    nation: str,
    password: str,
    nations: List[str],
    test: bool,
    title: Template,
    delegate: str,
    region: str,
    template_path: str,
):
    with open(template_path, "r") as in_file:
        dispatch_text = Template(in_file.read())

        if test:
            logger.info("test enabled, breaking nation tags")
            dispatch_text = dispatch_text.substitute(
                {"nations": ",".join(f"[nation]{nation}[nation]" for nation in nations)}
            )
        else:
            dispatch_text = dispatch_text.substitute(
                {
                    "nations": ",".join(
                        f"[nation]{nation}[/nation]" for nation in nations
                    ),
                }
            )

    title = title.substitute(
        {
            "delegate": delegate.replace("_", " ").title(),
            "region": region.title(),
            "date": date.today().strftime("%Y-%m-%d"),
        }
    )
    logger.info("publishing nne with title: %s", title)

    logger.debug("preparing")
    headers = {"User-Agent": user, "X-Password": password}

    data = {
        "nation": nation,
        "c": "dispatch",
        "dispatch": "add",
        "title": title,
        "text": dispatch_text,
        "category": 8,
        "subcategory": 845,
        "mode": "prepare",
    }

    resp = requests.post(
        "https://www.nationstates.net/cgi-bin/api.cgi", headers=headers, data=data
    )

    headers["X-Pin"] = resp.headers["X-Pin"]
    data["mode"] = "execute"
    data["token"] = bs(resp.text, "xml").SUCCESS.get_text()

    logger.debug("executing")
    requests.post(
        "https://www.nationstates.net/cgi-bin/api.cgi", headers=headers, data=data
    )


def main():
    conf = Config("./config.yml")
    logger.debug(conf)

    if not conf.delegate:
        logger.info("delegate not set, checking")
        conf.delegate = get_delegate(conf.user, conf.region)

    logger.info("pulling nations not endorsing %s", conf.delegate)
    nations_not_endorsing = get_nnes(conf.user, conf.region, conf.delegate)
    logger.debug("nations not endorsing: %d", len(nations_not_endorsing))

    if len(nations_not_endorsing) == 0:
        logger.info("all nations endorsing, terminating")
        return

    publish_nne(
        conf.user,
        conf.nation,
        conf.password,
        nations_not_endorsing,
        conf.test,
        conf.title,
        conf.delegate,
        conf.region,
        conf.template_path,
    )


if __name__ == "__main__":
    main()
