"""Recipe for deploying demoapp"""

from fabric.api import execute
from fabric.decorators import task

from orchalib import get_current_release_dir, get_app_basedir
from orchalib import tasks


@task
def print_app_version():
    """Print the currently deployed version info for the app."""
    execute(tasks.print_app_version, 'demoapp')


@task
def service_restart():
    """Restart services for this app."""
    execute(tasks.service_restart, 'demoapp')


@task
def deploy(uri=None, **_):
    """Deploy demoapp.

    Args:
        uri: The S3 URI for the application artifact to be deployed.
    """
    assert uri is not None

    app_name = 'demoapp'
    config_dir = '{}/config'.format(get_app_basedir(app_name))
    release_dir = get_current_release_dir(app_name)

    execute(tasks.local_fetch_s3_artifact, uri)
    execute(tasks.deploy_artifact, app_name, uri)
    execute(tasks.create_symlink,
            '{}/config.yml'.format(config_dir),
            '{}/config.yml'.format(release_dir))
    execute(tasks.service_restart, app_name)
