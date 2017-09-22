"""Helper routines that can be executed from tasks"""

from os import path

from fabric.api import env, execute, local, put, sudo
from fabric.context_managers import cd
from fabric.decorators import runs_once
from fabric.contrib import files

from . import (
    DEFAULT_OWNER,
    get_current_release_dir,
    get_temp_dir,
    get_app_basedir
)


@runs_once
def local_fetch_s3_artifact(uri, local_dest='.'):
    """Download a deployable from S3.
    Stages the S3 artifact locally on the deployer's system for later upload.

    Args:
        uri: An S3 URI to the artifact for deployment
    """
    local('aws s3 cp {} {}'.format(uri, local_dest))


def service_restart(appname):
    """Restart the specified service"""
    sudo('service {} restart'.format(appname))


def create_symlink(src, dest):
    """Create a symlink at `dest`, pointing to `src`."""
    sudo('ln -s {} {}'.format(src, dest))


def print_file(file_path):
    """Prints the printable characters in the specified file."""
    if files.exists(file_path):
        sudo('strings -n 1 {}'.format(file_path))
    else:
        print 'File not found: {}'.format(file_path)


def print_app_version(app_name):
    """Print the current version dot txt file for the given app_name."""
    print_file('{}/current/version.txt'.format(get_app_basedir(app_name)))


def delete_temp_dir(app_name):
    """Remove the temporary directory for storing fab deploy artifacts."""
    sudo('rm -rf /tmp/.fab-deploy-{}'.format(app_name))


def upload_build_artifact(filename, app_name):
    """Upload the build artifact from the localhost and place in the temp
    directory of the remote host.

    Args:
        filename: the filename of the build artifact
        temp_dir: the temporary directory to store source
    """
    temp_dir = get_temp_dir(app_name)

    # pre-clean and setup the remote upload directory
    sudo('rm -rf {}'.format(temp_dir))
    sudo('mkdir -p {}'.format(temp_dir))
    sudo('chown {} {}'.format(env['user'], temp_dir))

    # upload build artifact to host's temp_dir
    put(filename, temp_dir, mode=664)


def deploy_artifact(app_name, artifact_uri, owner=DEFAULT_OWNER):
    """Upload the deployable to the targeted host.

    Args:
        app_name: The name of the app to be deployed.
        artifact_uri: The path to the local artifact to be uploaded/deployed.
        owner: (optional) The desired user:group ownership of the
               deployed files.
    """
    artifact = path.basename(artifact_uri)

    upload_build_artifact(artifact, app_name)

    with cd(get_temp_dir(app_name)):
        # handle apps that use the 'current' symlink.
        vhost_dir = get_app_basedir(app_name)
        deploy_dir = get_current_release_dir(app_name)
        current_sym = '{}/current'.format(vhost_dir)

        # If a 'current' symlink exists, find out what it points to
        # and rotate it to 'prev'. If current is not a symlink, return
        # an error.
        if files.exists(current_sym):
            if files.is_link(current_sym):
                deploy_dir = sudo('readlink {}'.format(current_sym)).stdout
            else:
                raise Exception('[{}] is not a symlink?!?'.format(current_sym))

        # delete 'prev' release directory and rotate 'curr' to 'prev'
        # (only if 'current' wasn't pointing to 'prev')
        prev_dir = '{}/releases/prev'.format(vhost_dir)
        if deploy_dir != prev_dir:
            sudo('rm -rf {}'.format(prev_dir))
            if files.exists(deploy_dir):
                sudo('mv {} {}'.format(deploy_dir, prev_dir))

        # now, deploy new version into the 'curr' release directory
        sudo('mkdir -pv {}'.format(deploy_dir))
        sudo('tar -C {}/ -xzf {}'.format(deploy_dir, artifact))

        # it's possible 'current' isn't pointing at 'curr', so let's
        # fix it to point there now
        sudo('rm -fv {}'.format(current_sym))
        sudo('ln -svf {} {}'.format(deploy_dir, current_sym))

        # fix up file ownership on newly-deployed files
        sudo('chown -R {} {}'.format(owner, deploy_dir))

    delete_temp_dir(app_name)


def deploy_go_app(app_name, uri):
    """Common deployment recipe for Go applications.

    Args:
        app_name: the name of the Go application.
        uri: the build artifact URI.
    """
    execute(local_fetch_s3_artifact, uri)
    execute(deploy_artifact, app_name, uri)
    execute(create_symlink,
            '{}/config/config.yaml'.format(get_app_basedir(app_name)),
            '{}/etc/config.yaml'.format(get_current_release_dir(app_name)))
