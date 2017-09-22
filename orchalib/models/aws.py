"""Models for encapsulating AWS resource information"""

class Ec2Instance(object):
    """Contains configuration info for an EC2 instance, including the
    instance ID, IP address and tags

    """

    def __init__(self, instance_id, instance_ip, tags):
        self.instance_id = instance_id
        self.instance_ip = instance_ip

        self.tags = {}
        for tag in tags:
            self.tags[tag['Key']] = tag['Value']

    def __str__(self):
        return "%s, %s, %s" % (self.instance_id, self.instance_ip, repr(self.tags))

    def has_app(self, app):
        """Determine if the current EC2 instance is associated with the given
        app by examining the instance tags

        """
        try:
            appstr = self.tags['Apps']
            applist = appstr.split(',')
            return app in applist
        except KeyError:
            return False
