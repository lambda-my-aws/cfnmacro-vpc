cfnmacro-vpc
======

Macro to create a new VPC
-----

Overkill as it creates an entire VPC, the macro creates 1 subnet per AZ based on DescribeAzs.

Example of input template:

.. code-block:: yaml

   AWSTemplateFormatVersion: 2010-09-09

   Parameters:
     VpcCidr:
       Type: String
       Default: 10.242.0.0/22

   Transform:
     - cfnmacro-vpc


