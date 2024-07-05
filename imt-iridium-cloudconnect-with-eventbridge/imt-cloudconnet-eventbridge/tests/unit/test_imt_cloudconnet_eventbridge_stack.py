import aws_cdk as core
import aws_cdk.assertions as assertions

from imt_cloudconnet_eventbridge.imt_cloudconnet_eventbridge_stack import ImtCloudconnetEventbridgeStack

# example tests. To run these tests, uncomment this file along with the example
# resource in imt_cloudconnet_eventbridge/imt_cloudconnet_eventbridge_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = ImtCloudconnetEventbridgeStack(app, "imt-cloudconnet-eventbridge")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
