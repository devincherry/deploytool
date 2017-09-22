"""Helper functions for reading AWS EC2 instances and ELBs"""

from time import sleep
from datetime import date, timedelta
import boto3
from orchalib.models.aws import Ec2Instance
from botocore.exceptions import ClientError


DEBUG = False


def list_recent_artifacts(appname, numweeks):
    """Returns a list of artifacts based on YYYY.WW S3 prefix."""
    s3 = boto3.client("s3")
    this_week = date.today()
    this_week_str = this_week.strftime("%Y.%W")
    objects = {}
    artifact_urls = []
    while numweeks > 0:
        objects[this_week_str] = s3.list_objects_v2(Bucket='my-artifacts',
                                                    Prefix='{}/{}'.format(appname, this_week_str))
        this_week = this_week - timedelta(0, 0, 0, 0, 0, 0, 1)
        this_week_str = this_week.strftime("%Y.%W")
        numweeks = numweeks - 1
    for week in objects.keys():
        if objects[week]['IsTruncated']:
            print "WARNING: S3 bucket listing was truncated by AWS!"
        try:
            for item in objects[week]['Contents']:
                artifact_urls.append('s3://my-artifacts/{}'.format(item['Key']))
        except KeyError:
            # The API produces a response with no 'Contents' if no objects are found.
            pass
    return artifact_urls


def get_instances(environment=None):
    """Returns a list of Ec2Instance objects."""
    instances = []
    ec2 = boto3.client("ec2")

    if environment is not None:
        ec2_env_filter = {
            'Name': 'tag:Environment',
            'Values': [environment]
        }
        ec2_state_filter = {
            'Name': 'instance-state-name',
            'Values': ['running']
        }
        ec2_data = ec2.describe_instances(Filters=[ec2_env_filter, ec2_state_filter])
    else:
        ec2_data = ec2.describe_instances()

    for res in ec2_data['Reservations']:
        for i in res['Instances']:
            instances.append(Ec2Instance(i['InstanceId'], i['PrivateIpAddress'], i['Tags']))

    return instances


def get_elbs(app, env):
    """Returns a list of strings of elb names."""
    elbs = []
    elb_data = boto3.client('elb')

    for elb in elb_data.describe_load_balancers()['LoadBalancerDescriptions']:
        tags = elb_data.describe_tags(LoadBalancerNames=[elb['LoadBalancerName']])
        elb_tags = {tag['Key']: tag['Value'] for tag in tags['TagDescriptions'][0]['Tags']}
        if 'Environment' in elb_tags and elb_tags['Environment'] == env and \
           'Apps' in elb_tags and app in elb_tags['Apps'].split(','):
            elbs.append(elb['LoadBalancerName'])

    return elbs


def remove_instance_from_elb(load_balancer_name, instance_id):
    """Removes an instance from an ELB, and blocks until success or error."""
    elb = boto3.client("elb")

    # get ELB setting for connection draining timeout
    resp = elb.describe_load_balancer_attributes(LoadBalancerName=load_balancer_name)
    timeout = 0
    if resp['LoadBalancerAttributes']['ConnectionDraining']['Enabled']:
        timeout = resp['LoadBalancerAttributes']['ConnectionDraining']['Timeout']

    # for each instance, remove from ELB
    print "Removing instance [%s] from ELB [%s]..." % (instance_id, load_balancer_name)
    resp = elb.deregister_instances_from_load_balancer(
        LoadBalancerName=load_balancer_name,
        Instances=[
            {
                'InstanceId': instance_id
            },
        ]
    )

    if DEBUG:
        print resp

    try:
        resp = elb.describe_instance_health(
            LoadBalancerName=load_balancer_name,
            Instances=[
                {
                    'InstanceId': instance_id
                },
            ]
        )
    except ClientError, cle:
        error_code = cle.response['Error'].get('Code', 'Unknown')
        if error_code == 'InvalidInstance':
            print "De-registeration from ELB [{}] not required.".format(load_balancer_name)
            return
        else:
            raise cle

    if DEBUG:
        print resp

    elb_instance_state = resp['InstanceStates'][0]['State']

    # wait for connection draining to complete, if necessary
    if timeout > 0 and elb_instance_state != 'OutOfService':
        print "Waiting [%d] seconds for connection draining to complete..." % timeout

        while timeout > 0:
            print '. ',
            sleep(1)
            timeout -= 1
        print ''

        sleep(5)
        resp = elb.describe_instance_health(
            LoadBalancerName=load_balancer_name,
            Instances=[
                {
                    'InstanceId': instance_id
                },
            ]
        )

        if DEBUG:
            print resp

        if resp['InstanceStates'][0]['State'] != 'OutOfService':
            print "WARNING: Instance %s State is %s! Continuing." % (
                resp['InstanceStates'][0]['InstanceId'],
                resp['InstanceStates'][0]['State']
            )
        else:
            print "Instance [{}] has been deregistered from ELB [{}].".format(instance_id,
                                                                              load_balancer_name)


def add_instance_to_elb(load_balancer_name, instance_id):
    """Registers an instance in an ELB, and blocks until healthy or error."""
    elb = boto3.client("elb")

    print "Registering instance [%s] in ELB [%s]..." % (instance_id, load_balancer_name)
    resp = elb.register_instances_with_load_balancer(
        LoadBalancerName=load_balancer_name,
        Instances=[
            {
                'InstanceId': instance_id
            },
        ]
    )
    if DEBUG:
        print resp

    # wait until instance is healthy
    healthy = False

    # max time to wait for instance to become healthy
    max_wait = 300

    # pause time between checks
    check_delay = 5.0
    loop_count = max_wait/check_delay

    while not healthy:
        print '. ',
        sleep(check_delay)
        resp = elb.describe_instance_health(
            LoadBalancerName=load_balancer_name,
            Instances=[
                {
                    'InstanceId': instance_id
                },
            ]
        )

        if DEBUG:
            print resp

        if resp['InstanceStates'][0]['State'] == 'InService':
            healthy = True
            print "\nInstance [%s] is now [%s]" % (instance_id, resp['InstanceStates'][0]['State'])
        else:
            loop_count -= 1
            if loop_count <= 0:
                print "ERROR: Instance [{}] still unhealthy after [{}] seconds!".format(instance_id,
                                                                                        max_wait)
                raise Exception("Instance Not Healthy")
