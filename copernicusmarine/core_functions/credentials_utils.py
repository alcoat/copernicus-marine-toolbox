import base64
import configparser
import logging
import pathlib
from netrc import netrc
from platform import system
from typing import Literal, Optional, Tuple

import click
import lxml.html
import requests

from copernicusmarine.core_functions.environment_variables import (
    COPERNICUSMARINE_CREDENTIALS_DIRECTORY,
    COPERNICUSMARINE_SERVICE_PASSWORD,
    COPERNICUSMARINE_SERVICE_USERNAME,
)
from copernicusmarine.core_functions.sessions import (
    get_configured_requests_session,
)

logger = logging.getLogger("copernicusmarine")

USER_DEFINED_CACHE_DIRECTORY: str = (
    COPERNICUSMARINE_CREDENTIALS_DIRECTORY or ""
)
DEFAULT_CLIENT_BASE_DIRECTORY: pathlib.Path = (
    pathlib.Path(USER_DEFINED_CACHE_DIRECTORY)
    if USER_DEFINED_CACHE_DIRECTORY
    else pathlib.Path.home()
) / ".copernicusmarine"
DEFAULT_CLIENT_CREDENTIALS_FILENAME = ".copernicusmarine-credentials"
DEFAULT_CLIENT_CREDENTIALS_FILEPATH = (
    DEFAULT_CLIENT_BASE_DIRECTORY / DEFAULT_CLIENT_CREDENTIALS_FILENAME
)
RECOVER_YOUR_CREDENTIALS_MESSAGE = (
    "Learn how to recover your credentials at: "
    "https://help.marine.copernicus.eu/en/articles/"
    "4444552-i-forgot-my-username-or-my-password-what-should-i-do"
)

COPERNICUS_MARINE_AUTH_SYSTEM_URL = "https://auth.marine.copernicus.eu/"
COPERNICUS_MARINE_AUTH_SYSTEM_TOKEN_ENDPOINT = (
    COPERNICUS_MARINE_AUTH_SYSTEM_URL
    + "realms/MIS/protocol/openid-connect/token"
)
COPERNICUS_MARINE_AUTH_SYSTEM_USERINFO_ENDPOINT = (
    COPERNICUS_MARINE_AUTH_SYSTEM_URL
    + "realms/MIS/protocol/openid-connect/userinfo"
)


class CredentialsCannotBeNone(Exception):
    """
    Exception raised when credentials are not set.

    To use the Copernicus Marine Service, you need to provide a username and
    a password. You can set them as environment variables or pass them as
    arguments to the function or use the :func:`~copernicusmarine.login` command.
    To register and create your valid credentials, please visit:
    `copernicusmarine registration page <https://data.marine.copernicus.eu/register>`_
    """

    pass


class InvalidUsernameOrPassword(Exception):
    """
    Exception raised when the username or password are invalid.

    To register and create your valid credentials, please visit:
    `copernicusmarine registration page <https://data.marine.copernicus.eu/register>`_
    """

    pass


class CouldNotConnectToAuthenticationSystem(Exception):
    """
    Exception raised when the client could not connect to the authentication system.

    Please check the following common problems:

    - Check your internet connection
    - make sure to authorize ``cmems-cas.cls.fr`` and/or ``auth.marine.copernicus.eu`` domains

    If none of this worked, maybe the authentication system is down, please try again later.
    """  # noqa

    pass


def _load_credential_from_copernicus_marine_configuration_file(
    credential_type: Literal["username", "password"],
    configuration_filename: pathlib.Path,
) -> Optional[str]:
    configuration_file = open(configuration_filename)
    configuration_string = base64.standard_b64decode(
        configuration_file.read()
    ).decode("utf8")
    config = configparser.RawConfigParser()
    config.read_string(configuration_string)
    credential = config.get("credentials", credential_type)
    if credential:
        logger.debug(f"{credential_type} loaded from {configuration_filename}")
    return credential


def _load_credential_from_netrc_configuration_file(
    credential_type: Literal["username", "password"],
    configuration_filename: pathlib.Path,
    host: str,
) -> Optional[str]:
    authenticator = netrc(configuration_filename).authenticators(host=host)
    if authenticator:
        username, _, password = authenticator
        logger.debug(f"{credential_type} loaded from {configuration_filename}")
        return username if credential_type == "username" else password
    else:
        return None


def _load_credential_from_motu_configuration_file(
    credential_type: Literal["username", "password"],
    configuration_filename: pathlib.Path,
) -> Optional[str]:
    motu_file = open(configuration_filename)
    motu_credential_type = "user" if credential_type == "username" else "pwd"
    config = configparser.RawConfigParser()
    config.read_string(motu_file.read())
    credential = config.get("Main", motu_credential_type)
    if credential:
        logger.debug(f"{credential_type} loaded from {configuration_filename}")
    return credential


def _retrieve_credential_from_prompt(
    credential_type: Literal["username", "password"], hide_input: bool
) -> str:
    if credential_type == "username":
        logger.info(
            "Downloading Copernicus Marine data requires a Copernicus Marine username "
            "and password, sign up for free at:"
            " https://data.marine.copernicus.eu/register"
        )
    return click.prompt(
        "Copernicus Marine " + credential_type, hide_input=hide_input
    )


def _retrieve_credential_from_environment_variable(
    credential_type: Literal["username", "password"]
) -> Optional[str]:
    if credential_type == "username":
        logger.debug("Tried to load username from environment variable")
        return COPERNICUSMARINE_SERVICE_USERNAME
    if credential_type == "password":
        logger.debug("Tried to load password from environment variable")
        return COPERNICUSMARINE_SERVICE_PASSWORD


def _retrieve_credential_from_custom_configuration_files(
    credential_type: Literal["username", "password"],
    credentials_file: pathlib.Path,
    host: str = "default_host",
) -> Optional[str]:
    credential = _load_credential_from_copernicus_marine_configuration_file(
        credential_type, credentials_file
    )
    if not credential:
        credential = _load_credential_from_motu_configuration_file(
            credential_type, credentials_file
        )
        if not credential:
            credential = _load_credential_from_netrc_configuration_file(
                credential_type, credentials_file, host=host
            )
    return credential


def _retrieve_credential_from_default_configuration_files(
    credential_type: Literal["username", "password"],
    host: str = "default_host",
) -> Optional[str]:
    copernicus_marine_configuration_file = pathlib.Path(
        DEFAULT_CLIENT_CREDENTIALS_FILEPATH
    )
    motu_configuration_file = pathlib.Path(
        pathlib.Path.home() / "motuclient" / "motuclient-python.ini"
    )
    netrc_configuration_file = pathlib.Path(
        pathlib.Path.home() / ("_netrc" if system() == "Windows" else ".netrc")
    )
    if copernicus_marine_configuration_file.exists():
        credential = (
            _load_credential_from_copernicus_marine_configuration_file(
                credential_type,
                copernicus_marine_configuration_file,
            )
        )
    elif motu_configuration_file.exists():
        credential = _load_credential_from_motu_configuration_file(
            credential_type, motu_configuration_file
        )
    elif netrc_configuration_file.exists():
        credential = _load_credential_from_netrc_configuration_file(
            credential_type, netrc_configuration_file, host=host
        )
    else:
        credential = None
    return credential


def _retrieve_credential_from_configuration_files(
    credential_type: Literal["username", "password"],
    credentials_file: Optional[pathlib.Path],
    host: str = "default_host",
) -> Optional[str]:
    if credentials_file and credentials_file.exists():
        credential = _retrieve_credential_from_custom_configuration_files(
            credential_type, credentials_file, host
        )
    else:
        credential = _retrieve_credential_from_default_configuration_files(
            credential_type, host
        )
    return credential


def copernicusmarine_configuration_file_exists(
    configuration_file_directory: pathlib.Path,
) -> bool:
    configuration_filename = pathlib.Path(
        configuration_file_directory / DEFAULT_CLIENT_CREDENTIALS_FILENAME
    )
    return configuration_filename.exists()


def copernicusmarine_credentials_are_valid(
    configuration_file_directory: pathlib.Path,
    username: Optional[str],
    password: Optional[str],
):
    if username and password:
        if _are_copernicus_marine_credentials_valid(username, password):
            logger.info("Valid credentials from input username and password.")
            return True
        else:
            logger.info(
                "Invalid credentials from input username and password."
            )
            logger.info(RECOVER_YOUR_CREDENTIALS_MESSAGE)
            return False
    elif (
        COPERNICUSMARINE_SERVICE_USERNAME and COPERNICUSMARINE_SERVICE_PASSWORD
    ):
        if _are_copernicus_marine_credentials_valid(
            COPERNICUSMARINE_SERVICE_USERNAME,
            COPERNICUSMARINE_SERVICE_PASSWORD,
        ):
            logger.info(
                "Valid credentials from environment variables: "
                "COPERNICUSMARINE_SERVICE_USERNAME and "
                "COPERNICUSMARINE_SERVICE_PASSWORD."
            )
            return True
        else:
            logger.info(
                "Invalid credentials from environment variables: "
                "COPERNICUSMARINE_SERVICE_USERNAME and "
                "COPERNICUSMARINE_SERVICE_PASSWORD."
            )
            logger.info(RECOVER_YOUR_CREDENTIALS_MESSAGE)
            return False
    elif copernicusmarine_configuration_file_is_valid(
        configuration_file_directory
    ):
        logger.info("Valid credentials from configuration file.")
        return True
    else:
        logger.info("Invalid credentials from configuration file.")
        logger.info(RECOVER_YOUR_CREDENTIALS_MESSAGE)
    return False


def copernicusmarine_configuration_file_is_valid(
    configuration_file_directory: pathlib.Path,
) -> bool:
    if not copernicusmarine_configuration_file_exists(
        configuration_file_directory
    ):
        return False
    configuration_filename = pathlib.Path(
        configuration_file_directory / DEFAULT_CLIENT_CREDENTIALS_FILENAME
    )
    username = _retrieve_credential_from_configuration_files(
        "username", configuration_filename
    )
    password = _retrieve_credential_from_configuration_files(
        "password", configuration_filename
    )
    return (
        username is not None
        and password is not None
        and _are_copernicus_marine_credentials_valid(username, password)
    )


def create_copernicusmarine_configuration_file(
    username: str,
    password: str,
    configuration_file_directory: pathlib.Path,
    overwrite_configuration_file: bool,
) -> pathlib.Path:
    configuration_lines = [
        "[credentials]\n",
        f"username={username}\n",
        f"password={password}\n",
    ]
    configuration_filename = pathlib.Path(
        configuration_file_directory / DEFAULT_CLIENT_CREDENTIALS_FILENAME
    )
    if configuration_filename.exists() and not overwrite_configuration_file:
        click.confirm(
            f"File {configuration_filename} already exists, overwrite it ?",
            abort=True,
        )
    configuration_file_directory.mkdir(parents=True, exist_ok=True)
    configuration_file = open(configuration_filename, "w")
    configuration_string = base64.b64encode(
        "".join(configuration_lines).encode("ascii", "strict")
    ).decode("utf8")
    configuration_file.write(configuration_string)
    configuration_file.close()
    return configuration_filename


def _check_credentials_with_old_cas(username: str, password: str) -> bool:
    logger.debug("Checking user credentials...")
    service = "copernicus-marine-client"
    cmems_cas_login_url = (
        f"https://cmems-cas.cls.fr/cas/login?service={service}"
    )
    conn_session = get_configured_requests_session()
    login_session = conn_session.get(
        cmems_cas_login_url, proxies=conn_session.proxies
    )
    login_from_html = lxml.html.fromstring(login_session.text)
    hidden_elements_from_html = login_from_html.xpath(
        '//form//input[@type="hidden"]'
    )
    playload = {
        he.attrib["name"]: he.attrib["value"]
        for he in hidden_elements_from_html
    }
    playload["username"] = username
    playload["password"] = password
    logger.debug(f"POSTing credentials to {cmems_cas_login_url}...")
    login_response = conn_session.post(
        cmems_cas_login_url, data=playload, proxies=conn_session.proxies
    )
    login_success = 'class="success"' in login_response.text
    logger.debug("User credentials checked")
    return login_success


def _check_credentials_with_cas(username: str, password: str) -> bool:
    keycloak_url = COPERNICUS_MARINE_AUTH_SYSTEM_TOKEN_ENDPOINT
    client_id = "toolbox"
    scope = "openid profile email"

    data = {
        "client_id": client_id,
        "grant_type": "password",
        "username": username,
        "password": password,
        "scope": scope,
    }
    conn_session = get_configured_requests_session()
    response = conn_session.post(keycloak_url, data=data)
    response.raise_for_status()
    if response.status_code == 200:
        token_response = response.json()
        access_token = token_response["access_token"]
        userinfo_url = COPERNICUS_MARINE_AUTH_SYSTEM_USERINFO_ENDPOINT
        headers = {"Authorization": f"Bearer {access_token}"}
        response = conn_session.get(userinfo_url, headers=headers)
        response.raise_for_status()
        if response.status_code == 200:
            return True
        else:
            return False
    else:
        return False


def _are_copernicus_marine_credentials_valid_old_system(
    username: str, password: str
) -> bool:
    number_of_retry = 3
    user_is_active = None
    while (user_is_active not in [True, False]) and number_of_retry > 0:
        try:
            user_is_active = _check_credentials_with_old_cas(
                username=username, password=password
            )
        except requests.exceptions.ConnectTimeout:
            number_of_retry -= 1
        except requests.exceptions.ConnectionError:
            number_of_retry -= 1
    if user_is_active is None:
        raise CouldNotConnectToAuthenticationSystem()
    return user_is_active


def _are_copernicus_marine_credentials_valid(
    username: str, password: str
) -> bool:
    try:
        result = _are_copernicus_marine_credentials_valid_new_system(
            username, password
        )
        return result

    except Exception as e:
        logger.debug(
            f"Could not connect with new authentication system because of: {e}"
        )
        logger.debug("Trying with old authentication system...")
        return _are_copernicus_marine_credentials_valid_old_system(
            username, password
        )


def _are_copernicus_marine_credentials_valid_new_system(
    username: str, password: str
) -> bool:
    number_of_retry = 3
    user_is_active = None
    while (user_is_active not in [True, False]) and number_of_retry > 0:
        try:
            user_is_active = _check_credentials_with_cas(
                username=username, password=password
            )
        except requests.exceptions.ConnectTimeout:
            number_of_retry -= 1
        except requests.exceptions.ConnectionError:
            number_of_retry -= 1
    if user_is_active is None:
        raise CouldNotConnectToAuthenticationSystem()
    return user_is_active


def get_credential(
    credential: Optional[str],
    credential_type: Literal["username", "password"],
    hide_input: bool,
    credentials_file: Optional[pathlib.Path],
) -> str:
    if not credential:
        credential = _retrieve_credential_from_environment_variable(
            credential_type
        )
        if not credential:
            credential = _retrieve_credential_from_configuration_files(
                credential_type=credential_type,
                credentials_file=credentials_file,
                host="nrt.cmems-du.eu",
            )
            if not credential:
                credential = _retrieve_credential_from_configuration_files(
                    credential_type=credential_type,
                    credentials_file=credentials_file,
                    host="my.cmems-du.eu",
                )
                if not credential:
                    credential = _retrieve_credential_from_prompt(
                        credential_type, hide_input=hide_input
                    )
                    if not credential:
                        raise ValueError(f"{credential} cannot be None")
    else:
        logger.debug("Credentials loaded from function arguments")
    return credential


def get_and_check_username_password(
    username: Optional[str],
    password: Optional[str],
    credentials_file: Optional[pathlib.Path],
) -> Tuple[str, str]:
    username, password = get_username_password(
        username=username, password=password, credentials_file=credentials_file
    )
    copernicus_marine_credentials_are_valid = (
        _are_copernicus_marine_credentials_valid(
            username,
            password,
        )
    )
    if not copernicus_marine_credentials_are_valid:
        raise InvalidUsernameOrPassword(
            "Learn how to recover your credentials at: "
            "https://help.marine.copernicus.eu/en/articles/"
            "4444552-i-forgot-my-username-or-my-password-what-should-i-do"
        )
    return (username, password)


def get_username_password(
    username: Optional[str],
    password: Optional[str],
    credentials_file: Optional[pathlib.Path],
) -> Tuple[str, str]:
    username = get_credential(
        username,
        "username",
        hide_input=False,
        credentials_file=credentials_file,
    )
    password = get_credential(
        password,
        "password",
        hide_input=True,
        credentials_file=credentials_file,
    )
    return (username, password)


def _get_credential_from_environment_variable_or_prompt(
    credential: Optional[str],
    credential_type: Literal["username", "password"],
    hide_input: bool,
) -> str:
    if not credential:
        credential = _retrieve_credential_from_environment_variable(
            credential_type
        )
        if not credential:
            credential = _retrieve_credential_from_prompt(
                credential_type, hide_input
            )
            if not credential:
                raise CredentialsCannotBeNone(credential_type)
    return credential


def credentials_file_builder(
    username: Optional[str],
    password: Optional[str],
    configuration_file_directory: pathlib.Path,
    overwrite_configuration_file: bool,
) -> Optional[pathlib.Path]:
    username = _get_credential_from_environment_variable_or_prompt(
        username, "username", False
    )
    password = _get_credential_from_environment_variable_or_prompt(
        password, "password", True
    )
    copernicus_marine_credentials_are_valid = (
        _are_copernicus_marine_credentials_valid(username, password)
    )
    if copernicus_marine_credentials_are_valid:
        configuration_file = create_copernicusmarine_configuration_file(
            username=username,
            password=password,
            configuration_file_directory=configuration_file_directory,
            overwrite_configuration_file=overwrite_configuration_file,
        )
        return configuration_file
    return None
