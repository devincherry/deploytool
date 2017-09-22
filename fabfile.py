"""Fabfile contains main deployment task"""

from pkgutil import iter_modules
import yaml

from fabric.api import env, execute, task
from fabric.decorators import runs_once, hosts

import recipes
from orchalib import aws


DEBUG = False


def __read_config():
    ''' Loads deploytool's config options from a `config.yml`, if specified. '''
    cfg_file = open('config.yml', 'r')
    cfg = yaml.load(cfg_file.read())

    if cfg.has_key('env'):
        # load the builtin 'env' with custom values from global config
        for (key, val) in cfg['env'].items():
            env[key] = val

    if DEBUG:
        print env


def __get_instances_for_app(app_name, environment):
    ''' Returns a list of EC2 instances that have an `Apps` tag containing `app_name`. '''
    instances = []
    for i in aws.get_instances(environment=environment):
        if i.has_app(app_name):
            instances.append(i)
    return instances


def __load_recipe(app_name, cfg=None):
    ''' Returns the `recipe` module for the given `app_name`. '''
    recipe = None
    for (mod_loader, name, ispkg) in iter_modules(recipes.__path__, 'recipes.'):
        if name == 'recipes.' + app_name and not ispkg:
            loader = mod_loader.find_module(name, mod_loader.path)
            recipe = loader.load_module(name)

    if not recipe:
        print 'ERROR: no recipe found for [{}]'.format(app_name)
        exit(1)

    if cfg:
        try:
            execute(recipe.validate_config, cfg)
        except AssertionError as err:
            print 'ERROR: invalid config for {0}. Reason: field {1}.'.format(app_name, str(err))
            exit(1)

    return recipe


@task
def show_version(app_name, environment):
    """Prints out the deployed version of an app.

    Args:
        app_name:    The name of the application.
        environment: The environment for the specified app.
    """
    __read_config()
    recipe = __load_recipe(app_name)

    instances = __get_instances_for_app(app_name, environment)
    if not instances:
        print 'ERROR: no instances found!'
        exit(1)

    for i in instances:
        execute(recipe.print_app_version, hosts=[i.instance_ip])


@task
@runs_once
@hosts('127.0.0.1')
def show_artifacts(app_name, num_weeks=2):
    """Prints a listing of recent artifacts.

    Args:
        app_name:   The name of the app to fetch artifacts for.

    KW-Args:
        num_weeks:  The number of previous weeks to search. (default=2)
    """
    artifacts_list = aws.list_recent_artifacts(app_name, int(num_weeks))
    for path in artifacts_list:
        print path


@task
@runs_once
@hosts('127.0.0.1')
def restart_rolling(app_name, environment):
    """Performs a cluster-wide rolling restart of the app.

    Args:
        app_name:    The name of the app to restart.
        environment: The environment for the specified app.
    """
    __read_config()

    recipe = __load_recipe(app_name)

    ## get list of ELBs to bleed instances out-of/into
    elbs = aws.get_elbs(app_name, environment)
    if not elbs:
        print 'WARNING: No ELBs found for app. Continuing with rude restart...'

    ## get list of instances to bleed out-of/into the ELBs
    instances = __get_instances_for_app(app_name, environment)
    if not instances:
        print 'ERROR: no target instances found for service restart!'
        exit(1)

    ## iterate over instances, removing from ELBs, restarting, then re-registering into ELBs
    for i in instances:
        for elb_name in elbs:
            aws.remove_instance_from_elb(elb_name, i.instance_id)

        execute(recipe.service_restart, hosts=[i.instance_ip])

        for elb_name in elbs:
            aws.add_instance_to_elb(elb_name, i.instance_id)


@task
@runs_once
@hosts('127.0.0.1')
def deploy_rolling(app_name, environment, artifact_uri=None, cfg=None):
    """Does a rolling deployment of the given app.

    Args:
        app_name:     The name of the app/recipe to deploy.
        environment:  The environment (i.e. dev|stg|prd) to deploy to.

    KW-Args:
        artifact_uri: An S3 URL for the artifact to deploy (used by some recipes).
        cfg:         A custom JSON config to pass to the deploy recipe (either
                     a filename or raw json string).
    """
    __read_config()

    if cfg and artifact_uri:
        raise Exception("The `cfg` and `artifact_uri` options are mutually exclusive!")

    recipe = __load_recipe(app_name, cfg)

    ## get list of ELBs to bleed instances out-of/into during deployment
    elbs = aws.get_elbs(app_name, environment)
    if not elbs:
        print 'WARNING: No ELBs found for app. Continuing with rude deployment...'

    ## get list of instances to bleed out-of/into the ELBs
    instances = __get_instances_for_app(app_name, environment)
    if not instances:
        print 'ERROR: no target instances found for deployment!'
        exit(1)

    ## iterate over instances, removing from ELBs, deploying, then re-registering into ELBs
    for i in instances:
        for elb_name in elbs:
            aws.remove_instance_from_elb(elb_name, i.instance_id)

        if cfg:
            execute(recipe.deploy, cfg=cfg, hosts=[i.instance_ip])
        else:
            execute(recipe.deploy, uri=artifact_uri, hosts=[i.instance_ip])

        for elb_name in elbs:
            aws.add_instance_to_elb(elb_name, i.instance_id)
