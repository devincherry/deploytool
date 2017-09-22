"""Various helper routines and constants for use in deployment"""

import json

from requests import codes


DEFAULT_OWNER = 'ci:www-data'


def is_response_valid(res):
    """Return boolean indicating response is valid or not.

    Args:
        res: a requests.model.Response

    Returns:
        boolean
    """
    return res.status_code >= codes.ok and res.status_code < codes.multiple_choices


def read_json_config(cfg):
    """Read a JSON configuration. First attempt to read as a JSON
    string. If that fails, assume that it is a JSON file and attempt
    to read contents from the file.

    Args:
        res: a config string or file path

    Returns:
        dict of config options
    """
    try:
        cfg = json.loads(cfg)
    except ValueError:
        cfg_file = open(cfg, 'r')
        cfg = json.load(cfg_file)

    return cfg


def get_temp_dir(app_name):
    """Get the temporary directory for storing fab deploy artifacts.

    Args:
        app_name: a string representing the app name

    Returns:
        a string representing path to tmp dir
    """
    return '/tmp/.fab-deploy-{}'.format(app_name)


def get_app_basedir(app_name):
    """Get the base deployment directory for the specified app.

    Args:
        app_name: a string representing the app name

    Returns:
        a string representing path to the app's basedir
    """
    return '/var/www/apps/{}'.format(app_name)


def get_current_release_dir(app_name):
    """Get the current release directory for the specified app name, For
    apps that utilize a symlink and a curr/prev rotation for rollbacks.

    Args:
        app_name: a string representing the app name

    Returns:
        a string representing path to current release
    """
    return '{}/releases/curr'.format(get_app_basedir(app_name))
