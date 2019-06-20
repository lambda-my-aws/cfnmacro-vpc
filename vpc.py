#!/usr/bin/env python

import os
import sys

from troposphere import (
     Parameter, Template,
     Output, GetAtt,
     Tags, Join,
     Ref, Sub,
     FindInMap,
)

from troposphere import (
     Equals, Not,
     Condition
)

from troposphere.ssm import (
     Parameter as SSMParam
)

from troposphere.servicediscovery import (
     Instance as MapInstance,
     PrivateDnsNamespace as VpcSpace,
)

from troposphere.route53 import (
     AliasTarget,
     HostedZoneConfiguration,
     HostedZoneVPCs,
     HostedZone
)


from troposphere.ec2 import (
     VPC as VPCType, VPCGatewayAttachment,
     VPCEndpoint, VPCEndpointConnectionNotification,
     VPCEndpointService, VPCEndpointServicePermissions,
     Subnet, SubnetRouteTableAssociation, SubnetNetworkAclAssociation,
     Route, RouteTable,
     InternetGateway, EgressOnlyInternetGateway, NatGateway,
     SecurityGroup, SecurityGroupRule, PortRange, NetworkAcl, NetworkAclEntry,
     NetworkInterfaceProperty, EIP, FlowLog,
     DHCPOptions, VPCDHCPOptionsAssociation
)

from ozone.outputs import object_outputs, comments_outputs
from string import ascii_lowercase as alpha
from troposphere.s3 import (
     BucketPolicy,
     Bucket
)

from ozone.resources.s3.bucket import S3Bucket

def generate_vpc_template(layers, az_count, cidr_block):
     TPL = Template()
     TPL.set_description('VPC - Version 2019-06-05')
     TPL.set_metadata({
               'Author': 'https://github.com/johnpreston'
     })
     VPC = VPCType(
          'VPC',
          CidrBlock=cidr_block,
          EnableDnsHostnames=True,
          EnableDnsSupport=True,
          Tags=Tags(
               Name=Ref('AWS::StackName'),
               EnvironmentName=Ref('AWS::StackName')
          )
     )
     IGW = InternetGateway("InternetGateway")
     IGW_ATTACH = VPCGatewayAttachment(
          "VPCGatewayAttachement",
          InternetGatewayId=Ref(IGW),
          VpcId=Ref(VPC)
     )
     DHCP_OPTIONS = DHCPOptions(
          'VpcDhcpOptions',
          DomainName=Sub(f'${{AWS::StackName}}.local'),
          DomainNameServers=['AmazonProvidedDNS'],
          Tags=Tags(
               Name=Sub(f'DHCP-${{{VPC.title}}}')
          )
     )
     DHCP_ATTACH = VPCDHCPOptionsAssociation(
          'VpcDhcpOptionsAssociate',
          DhcpOptionsId=Ref(DHCP_OPTIONS),
          VpcId=Ref(VPC)
     )
     DNS_HOSTED_ZONE = HostedZone(
          'VpcHostedZone',
          VPCs=[
               HostedZoneVPCs(
                    VPCId=Ref(VPC),
                    VPCRegion=Ref('AWS::Region')
               )
          ],
          Name=Sub(f'${{AWS::StackName}}.local'),
          HostedZoneTags=Tags(Name=Sub(f'ZoneFor-${{{VPC.title}}}'))
     )
     TPL.add_resource(VPC)
     TPL.add_resource(IGW)
     TPL.add_resource(IGW_ATTACH)
     TPL.add_resource(DHCP_OPTIONS)
     TPL.add_resource(DHCP_ATTACH)
     TPL.add_resource(DNS_HOSTED_ZONE)
     STORAGE_RTB = TPL.add_resource(RouteTable(
          'StorageRtb',
          VpcId=Ref(VPC),
          Tags=Tags(Name='StorageRtb')
     ))
     STORAGE_SUBNETS = []
     for count, subnet_cidr in zip(az_count, layers['stor']):
          subnet = Subnet(
               f'StorageSubnet{alpha[count].upper()}',
               CidrBlock=subnet_cidr,
               VpcId=Ref(VPC),
               AvailabilityZone=Sub(f'${{AWS::Region}}{alpha[count]}'),
               Tags=Tags(
                    Name=Sub(f'${{AWS::StackName}}-Storage-{alpha[count]}'),
                    Usage="Storage"
               )
          )
          subnet_assoc = TPL.add_resource(SubnetRouteTableAssociation(
               f'StorageSubnetAssoc{alpha[count].upper()}',
               SubnetId=Ref(subnet),
               RouteTableId=Ref(STORAGE_RTB)
          ))
          STORAGE_SUBNETS.append(subnet)
          TPL.add_resource(subnet)
     PUBLIC_RTB = TPL.add_resource(RouteTable(
          'PublicRtb',
          VpcId=Ref(VPC),
          Tags=Tags(Name='PublicRtb')
     ))
     PUBLIC_ROUTE = TPL.add_resource(Route(
          'PublicDefaultRoute',
          GatewayId=Ref(IGW),
          RouteTableId=Ref(PUBLIC_RTB),
          DestinationCidrBlock='0.0.0.0/0'
     ))
     PUBLIC_SUBNETS = []
     NAT_GATEWAYS = []
     for count, subnet_cidr in zip(az_count, layers['pub']):
          subnet = Subnet(
               f'PublicSubnet{alpha[count].upper()}',
               CidrBlock=subnet_cidr,
               VpcId=Ref(VPC),
               AvailabilityZone=Sub(f'${{AWS::Region}}{alpha[count]}'),
               MapPublicIpOnLaunch=True,
               Tags=Tags(Name=Sub(f'${{AWS::StackName}}-Public-{alpha[count]}'))
          )
          eip = TPL.add_resource(EIP(
               f"NatGatewayEip{alpha[count].upper()}",
               Domain='vpc'
          ))
          nat = NatGateway(
               f"NatGatewayAz{alpha[count].upper()}",
               AllocationId=GetAtt(eip, 'AllocationId'),
               SubnetId=Ref(subnet)
          )
          subnet_assoc = TPL.add_resource(SubnetRouteTableAssociation(
               f'PublicSubnetsRtbAssoc{alpha[count].upper()}',
               RouteTableId=Ref(PUBLIC_RTB),
               SubnetId=Ref(subnet)
          ))
          NAT_GATEWAYS.append(nat)
          PUBLIC_SUBNETS.append(subnet)
          TPL.add_resource(nat)
          TPL.add_resource(subnet)
     APP_SUBNETS = []
     APP_RTBS = []
     for count, subnet_cidr, nat in zip(az_count, layers['app'], NAT_GATEWAYS):
          SUFFIX = alpha[count].upper()
          subnet = Subnet(
               f'AppSubnet{SUFFIX}',
               CidrBlock=subnet_cidr,
               VpcId=Ref(VPC),
               AvailabilityZone=Sub(f'${{AWS::Region}}{alpha[count]}'),
               Tags=Tags(Name=Sub(f'${{AWS::StackName}}-App-{alpha[count]}'))
          )
          APP_SUBNETS.append(subnet)
          rtb = RouteTable(
               f'AppRtb{alpha[count].upper()}',
               VpcId=Ref(VPC),
               Tags=Tags(Name=f'AppRtb{alpha[count].upper()}')
          )
          APP_RTBS.append(rtb)
          route = Route(
               f'AppRoute{alpha[count].upper()}',
               NatGatewayId=Ref(nat),
               RouteTableId=Ref(rtb),
               DestinationCidrBlock='0.0.0.0/0'
          )
          subnet_assoc = SubnetRouteTableAssociation(
               f'SubnetRtbAssoc{alpha[count].upper()}',
               RouteTableId=Ref(rtb),
               SubnetId=Ref(subnet)
          )
          TPL.add_resource(subnet)
          TPL.add_resource(rtb)
          TPL.add_resource(route)
          TPL.add_resource(subnet_assoc)

     APP_S3_ENDPOINT = VPCEndpoint(
          'AppS3Endpoint',
          VpcId=Ref(VPC),
          RouteTableIds=[Ref(rtb) for rtb in APP_RTBS],
          ServiceName=Sub('com.amazonaws.${AWS::Region}.s3'),
          VpcEndpointType='Gateway',
     )
     PUBLIC_S3_ENDPOINT = VPCEndpoint(
          'PublicS3Endpoint',
          VpcId=Ref(VPC),
          RouteTableIds=[Ref(PUBLIC_RTB)],
          ServiceName=Sub('com.amazonaws.${AWS::Region}.s3'),
          VpcEndpointType='Gateway',
     )
     STORAGE_S3_ENDPOINT = VPCEndpoint(
          'StorageS3Endpoint',
          VpcId=Ref(VPC),
          RouteTableIds=[Ref(STORAGE_RTB)],
          ServiceName=Sub('com.amazonaws.${AWS::Region}.s3'),
          VpcEndpointType='Gateway')
     RESOURCES = []
     for count in az_count:
          resource = TPL.add_resource(EIP(
               f'Eip{count}',
               Domain='vpc'
          ))
          RESOURCES.append(resource)
     TPL.add_resource(APP_S3_ENDPOINT)
     TPL.add_resource(PUBLIC_S3_ENDPOINT)
     TPL.add_resource(STORAGE_S3_ENDPOINT)
     SG_RULES = []
     for subnet in layers['app']:
          RULE = SecurityGroupRule(
               IpProtocol="tcp",
               FromPort="443",
               ToPort="443",
               CidrIp=subnet,
          )
          SG_RULES.append(RULE)

     ENDPOINT_SG = TPL.add_resource(SecurityGroup(
          'VpcEndpointSecurityGroup',
          VpcId=Ref(VPC),
          GroupDescription='SG for all Interface VPC Endpoints',
          SecurityGroupIngress=SG_RULES,
          Tags=Tags(Name="sg-endpoints"),
     ))

     APP_SNS_ENDPOINT = VPCEndpoint(
          'AppSNSEndpoint',
          VpcId=Ref(VPC),
          SubnetIds=[Ref(subnet) for subnet in APP_SUBNETS],
          SecurityGroupIds=[
               GetAtt(ENDPOINT_SG, 'GroupId')
          ],
          ServiceName=Sub('com.amazonaws.${AWS::Region}.sns'),
          VpcEndpointType='Interface',
          PrivateDnsEnabled=True
     )
     TPL.add_resource(APP_SNS_ENDPOINT)

     APP_SQS_ENDPOINT = VPCEndpoint(
          'AppSQSEndpoint',
          VpcId=Ref(VPC),
          SubnetIds=[Ref(subnet) for subnet in APP_SUBNETS],
          SecurityGroupIds=[
               GetAtt(ENDPOINT_SG, 'GroupId')
          ],
          ServiceName=Sub('com.amazonaws.${AWS::Region}.sqs'),
          VpcEndpointType='Interface',
          PrivateDnsEnabled=True
     )
     TPL.add_resource(APP_SQS_ENDPOINT)

     APP_ECR_API_ENDPOINT = VPCEndpoint(
          'AppECRAPIEndpoint',
          VpcId=Ref(VPC),
          SubnetIds=[Ref(subnet) for subnet in APP_SUBNETS],
          SecurityGroupIds=[
               GetAtt(ENDPOINT_SG, 'GroupId')
          ],
          ServiceName=Sub('com.amazonaws.${AWS::Region}.ecr.api'),
          VpcEndpointType='Interface',
          PrivateDnsEnabled=True
     )
     TPL.add_resource(APP_ECR_API_ENDPOINT)

     APP_ECR_DKR_ENDPOINT = VPCEndpoint(
          'AppECRDKREndpoint',
          VpcId=Ref(VPC),
          SubnetIds=[Ref(subnet) for subnet in APP_SUBNETS],
          SecurityGroupIds=[
               GetAtt(ENDPOINT_SG, 'GroupId')
          ],
          ServiceName=Sub('com.amazonaws.${AWS::Region}.ecr.dkr'),
          VpcEndpointType='Interface',
          PrivateDnsEnabled=True
     )
     TPL.add_resource(APP_ECR_DKR_ENDPOINT)

     APP_SECRETS_MANAGER_ENDPOINT = VPCEndpoint(
          'AppSecretsManagerEndpoint',
          VpcId=Ref(VPC),
          SubnetIds=[Ref(subnet) for subnet in APP_SUBNETS],
          SecurityGroupIds=[
               GetAtt(ENDPOINT_SG, 'GroupId')
          ],
          ServiceName=Sub('com.amazonaws.${AWS::Region}.secretsmanager'),
          VpcEndpointType='Interface',
          PrivateDnsEnabled=True
     )
     TPL.add_resource(APP_SECRETS_MANAGER_ENDPOINT)

     APP_SSM_ENDPOINT = VPCEndpoint(
          'AppSSMEndpoint',
          VpcId=Ref(VPC),
          SubnetIds=[Ref(subnet) for subnet in APP_SUBNETS],
          SecurityGroupIds=[
               GetAtt(ENDPOINT_SG, 'GroupId')
          ],
          ServiceName=Sub('com.amazonaws.${AWS::Region}.ssm'),
          VpcEndpointType='Interface',
          PrivateDnsEnabled=True
     )
     TPL.add_resource(APP_SSM_ENDPOINT)

     APP_SSM_MESSAGES_ENDPOINT = VPCEndpoint(
          'AppSSMMessagesEndpoint',
          VpcId=Ref(VPC),
          SubnetIds=[Ref(subnet) for subnet in APP_SUBNETS],
          SecurityGroupIds=[
               GetAtt(ENDPOINT_SG, 'GroupId')
          ],
          ServiceName=Sub('com.amazonaws.${AWS::Region}.ssmmessages'),
          VpcEndpointType='Interface',
          PrivateDnsEnabled=True
     )
     TPL.add_resource(APP_SSM_MESSAGES_ENDPOINT)

     ################################################################################
     #
     # OUTPUTS
     #
     TPL.add_output(object_outputs(VPC, name_is_id=True))
     TPL.add_output(object_outputs(APP_SQS_ENDPOINT, name_is_id=True))
     TPL.add_output(object_outputs(APP_SNS_ENDPOINT, name_is_id=True))
     TPL.add_output(comments_outputs(
          [
               {'EIP': Join(',', [GetAtt(resource, "AllocationId") for resource in RESOURCES])},
               {'PublicSubnets': Join(',', [Ref(subnet) for subnet in PUBLIC_SUBNETS])},
               {'StorageSubnets': Join(',', [Ref(subnet) for subnet in STORAGE_SUBNETS])},
               {'ApplicationSubnets': Join(',', [Ref(subnet) for subnet in APP_SUBNETS])},
               {'StackName': Ref('AWS::StackName')},
               {'VpcZoneId': Ref(DNS_HOSTED_ZONE)}
          ]
     ))
     return TPL
