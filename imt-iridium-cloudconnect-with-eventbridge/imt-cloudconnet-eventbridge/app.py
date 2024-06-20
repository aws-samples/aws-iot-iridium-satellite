#!/usr/bin/env python3
import os

import aws_cdk as cdk

from imt_cloudconnet_eventbridge.imt_cloudconnet_eventbridge_stack import ImtCloudconnetEventbridgeStack

app = cdk.App()

ImtCloudconnetEventbridgeStack(app, "ImtCloudconnetEventbridgeStack")

app.synth()