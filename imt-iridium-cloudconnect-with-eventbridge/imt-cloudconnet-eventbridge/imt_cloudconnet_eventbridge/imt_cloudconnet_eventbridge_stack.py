import json
from aws_cdk import (
    Stack,
    aws_events as events,
    aws_events_targets as targets,
    aws_sqs as sqs,
    aws_apigateway as apigw,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_pipes as pipes,
    aws_logs as logs,
    aws_iot_alpha as iot,
    aws_iot_actions_alpha as actions,
    CfnParameter
)

from constructs import Construct

class ImtCloudconnetEventbridgeStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        ########################################################################################################
        ##### CfnParameter START ###############################################################################
        ########################################################################################################

        IoTSubDomain = CfnParameter(self, "IoTSubDomain", type="String",
            description="The IoT-Data endpoint subdomain. Example: a2ydopmexample-ats")
        
        IoTRegion = CfnParameter(self, "IoTRegion", type="String",
            description="The application region. Example: eu-west-1")
        
        IoTAccount = CfnParameter(self, "IoTAccount", type="String",
            description="Account for this stack to be depoyed in. Example: 1234525454364")
        
        ImtQueueImtmoArn = CfnParameter(self, "ImtQueueImtmoArn", type="String",
            description="IMTMO Queue. Example: arn:aws:sqs:eu-west-1:123456789012:IMTMO.fifo")
        
        ImtQueueImtmtArn = CfnParameter(self, "ImtQueueImtmtArn", type="String",
            description="IMTMO Queue. Example: arn:aws:sqs:eu-west-1:123456789012:IMTMT.fifo")
        
        ImtQueueImtStatusArn = CfnParameter(self, "ImtQueueImtStatusArn", type="String",
            description="IMTSTATUS Queue. Example: arn:aws:sqs:eu-west-1:123456789012:IMTSTATUS.fifo")
        
        ImtIoTPrefix = CfnParameter(self, "ImtIoTPrefix", type="String",
            description="IoT prefix used when publishing MO messages to IoT Core. Example: CloudConnect")
        
        ImtTopicId = CfnParameter(self, "ImtTopicId", type="String",
            description="Topic Id provided by Iridium. Example: 123")
        

    ########################################################################################################
    ##### MO START #########################################################################################
    ########################################################################################################

        # Create role for API gateway to use when publishing to iot
        imt_iot_api_role = iam.Role(
            self,"imt_iot_api_role",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com")
        )
        
        imt_iot_api_role_resource = "arn:aws:iot:" + IoTRegion.value_as_string + ":" + IoTAccount.value_as_string + ":topic/" + ImtIoTPrefix.value_as_string + "/*/mo"

        imt_iot_api_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=[imt_iot_api_role_resource],
            actions=[
                "iot:Publish"
            ]
        ))
        
        # Create integration for API gateway to publish to iot
        imt_mo_message_integration_request_iot_core = apigw.AwsIntegration(
            service="iotdata",
            integration_http_method="POST",
            path="topics/"+ImtIoTPrefix.value_as_string+"/{cmid}/mo?qos=1", # {cmid} is a path parameter
            subdomain=IoTSubDomain.value_as_string,
            region=IoTRegion.value_as_string,
            options=apigw.IntegrationOptions(
                request_parameters={"integration.request.path.cmid": "method.request.path.cmid"},
                integration_responses=[
                    apigw.IntegrationResponse(
                        status_code="200",
                        response_templates={"application/json": ""}
                    )
                ],
                credentials_role=imt_iot_api_role
                
            )
        )
    
        # Create IoT api gateway
        imt_iot_api = apigw.RestApi(self, "imt_iot_api")

        # Add /{cmid} path/resource
        imt_iot_api_resouce = imt_iot_api.root.add_resource("{cmid}")
    
        # Add method to API gateway
        imt_iot_api_resouce.add_method(
            "POST", 
            imt_mo_message_integration_request_iot_core, 
            method_responses=[apigw.MethodResponse(status_code="200")],
            request_parameters={"method.request.path.cmid": False},
            authorization_type=apigw.AuthorizationType.IAM
        )

        # Create DynamoDB table
        imt_mo_table = dynamodb.Table(self, "imt_mo_table",
            partition_key=dynamodb.Attribute(name="cmid", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="transmissionEndTime", type=dynamodb.AttributeType.STRING)
        )

        # Create role for API gateway to use when publishing to dynamoDB
        imt_dynamodb_api_api_role = iam.Role(
            self,"imt_dynamodb_api_api_role",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com")
        )
        imt_dynamodb_api_api_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=[imt_mo_table.table_arn],
            actions=[
                "dynamodb:PutItem"
            ]
        ))
 
        imt_dynamodb_equest_template = """{ 
                "TableName": \""""+ imt_mo_table.table_name + """\",
                "Item": {
                    "billingReference": {
                        "S": "$input.path('$.detail.body.billingReference')"
                        },
                    "cmid": {
                        "S": "$method.request.path.cmid"
                        },
                    "location": {
                        "S": "$input.path('$.detail.body.location')"
                    },
                    "messageId": {
                        "N": "$input.path('$.detail.body.messageId')"
                    },
                    "originatorCrcError": {
                        "BOOL": "$input.path('$.detail.body.originatorCrcError')"
                    },
                    "payload": {
                        "S": "$input.path('$.detail.body.payload')"
                    },
                    "topicId": {
                        "N": "$input.path('$.detail.body.topicId')"
                    },
                    "transmissionEndTime": {
                        "S": "$input.path('$.detail.body.transmissionEndTime')"
                    }
                    ,
                    "transmissionStartTime": {
                        "S": "$input.path('$.detail.body.transmissionStartTime')"
                    },
                    "version": {
                        "S": "$input.path('$.detail.body.version')"
                    }
                }
            }"""

        imt_mo_message_integration_dynamodb = apigw.AwsIntegration(
            service="dynamodb",
            action="PutItem",
            region=IoTRegion.value_as_string,
            options=apigw.IntegrationOptions(
                request_parameters={"integration.request.path.cmid": "method.request.path.cmid"},
                integration_responses=[
                    apigw.IntegrationResponse(
                        status_code="200"
                    )
                ],
                credentials_role=imt_dynamodb_api_api_role,
                request_templates={"application/json": imt_dynamodb_equest_template}
            )
        )

        # Create DynamoDB api gateway
        imt_dynamodb_api = apigw.RestApi(self, "imt_dynamodb_api")

        # Add /{cmid} path/resource
        imt_dynamodb_api_resource = imt_dynamodb_api.root.add_resource("{cmid}")
        
        # Add method to API gateway
        imt_dynamodb_api_resource.add_method(
            "POST", 
            imt_mo_message_integration_dynamodb, 
            method_responses=[apigw.MethodResponse(status_code="200")],
            request_parameters={"method.request.path.cmid": False},
            authorization_type=apigw.AuthorizationType.IAM
        )
        
        # Create new bus
        imt_bus = events.EventBus(self, "bus", event_bus_name="imt-bus")

        # Create rule to capture messages coming fom imt_mo pipe
        imt_mo_rule = events.Rule(self, "imt_mo_rule",
            event_bus = imt_bus,
            event_pattern=events.EventPattern(
                account=[Stack.of(self).account],
                source=["Pipe IMTMO_DEV"],
            )
        )
        # Create rule target for Iot
        imt_mo_rule.add_target(
            targets.ApiGateway(imt_iot_api,
                path="/*",
                method="POST",
                stage="prod",
                path_parameter_values=["$.detail.body.cmid"]
        ))
        
        # Create rule target for DynamoDB
        imt_mo_rule.add_target(
            targets.ApiGateway(imt_dynamodb_api,
                path="/*",
                method="POST",
                stage="prod",
                path_parameter_values=["$.detail.body.cmid"]
        ))

        # Create role for API gateway to use when publishing to iot
        imt_pipes_imtmo_role = iam.Role(
            self,"imt_pipes_imtmo_role",
            assumed_by=iam.ServicePrincipal("pipes.amazonaws.com")
        )
        
        # Add permissions to publish to the event bus
        imt_pipes_imtmo_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=[imt_bus.event_bus_arn],
            actions=[
                "events:PutEvents"
            ]
        ))
        # Add permissions to receive and delete messages from the IMTMO Queue
        imt_pipes_imtmo_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=[ImtQueueImtmoArn.value_as_string],
            actions=[
                "sqs:ReceiveMessage",
                "sqs:DeleteMessage",
                "sqs:GetQueueAttributes"
            ]
        ))
      
        # Create the log group
        imt_pipes_imtmt_pre_log_group = logs.LogGroup(self, "/aws/vendedlogs/pipes/IMTMO_DEV")

        # Allow publishing to the log group
        imt_pipes_imtmo_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=[imt_pipes_imtmt_pre_log_group.log_group_arn],
            actions=[
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
                "logs:DescribeLogGroups",
                "logs:DescribeLogStreams"
            ]
        ))

        # Create a pipe conencting SQS IMTMO woith the event bus
        imt_imtmo_pipe = pipes.CfnPipe(self, "imt_imtmo_pipe",
                role_arn=imt_pipes_imtmo_role.role_arn,
                source=ImtQueueImtmoArn.value_as_string,
                source_parameters=pipes.CfnPipe.PipeSourceParametersProperty(
                    sqs_queue_parameters=pipes.CfnPipe.PipeSourceSqsQueueParametersProperty(
                        batch_size=1
                    )
                ),
                target=imt_bus.event_bus_arn,
                target_parameters=pipes.CfnPipe.PipeTargetParametersProperty(
                    input_template=" { \"body\": <$.body>, \"attributes\": <$.attributes> } "
                ),
                name="IMTMO_DEV",
                log_configuration=pipes.CfnPipe.PipeLogConfigurationProperty(
                    cloudwatch_logs_log_destination=pipes.CfnPipe.CloudwatchLogsLogDestinationProperty(
                        log_group_arn=imt_pipes_imtmt_pre_log_group.log_group_arn
                    ),
                    level="TRACE" # TRACE, INFO, ERROR
                )
        )

      
         
    ########################################################################################################
    ##### MT START #########################################################################################
    ########################################################################################################

        # Create DynamoDB Table for MT
        imt_mt_table2 = dynamodb.TableV2(self, "imt_mt_table2",
            partition_key=dynamodb.Attribute(name="cmid", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="ts", type=dynamodb.AttributeType.NUMBER),
            dynamo_stream=dynamodb.StreamViewType.NEW_IMAGE,
        )

        # Create Q IMTMT-PRE
        imt_mt_pre_queue = sqs.Queue(self, "imt_mt_pre_queue",
            queue_name="imt_mt_pre_queue"
        )


        # Create role assumed by the pipe and used to send messages to the bus
        imt_imtmt_pre_pipe_role = iam.Role(
            self,"imt_imtmt_pre_pipe_role",
            assumed_by=iam.ServicePrincipal("pipes.amazonaws.com")
        )

        # Add permissions to publish to the event bus
        imt_imtmt_pre_pipe_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=[imt_bus.event_bus_arn],
            actions=[
                "events:PutEvents"
            ]
        ))

        # Add permissions to get data coming from DynamoDB stream
        imt_imtmt_pre_pipe_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=[imt_mt_table2.table_stream_arn],
            actions=[
                "dynamodb:DescribeStream",
                "dynamodb:GetRecords",
                "dynamodb:GetShardIterator",
                "dynamodb:ListStreams"
            ]
        ))

         # Create the log group
        imt_pipes_imtmt_pre_log_group = logs.LogGroup(self, "/aws/vendedlogs/pipes/IMTMT_PRE_DEV")
        
        # Create pipe that takes data from DynamoDB and delivers it to imt-bus
        imt_imtmt_pre_pipe = pipes.CfnPipe(self, "imt_imtmt_pre_pipe",
                name="IMTMT_PRE_DEV",
                role_arn=imt_imtmt_pre_pipe_role.role_arn,
                source=imt_mt_table2.table_stream_arn,
                source_parameters=pipes.CfnPipe.PipeSourceParametersProperty(
                    dynamo_db_stream_parameters=pipes.CfnPipe.PipeSourceDynamoDBStreamParametersProperty(
                        batch_size=1,
                        starting_position="LATEST"
                    )
                ),
                target=imt_bus.event_bus_arn,
                # target_parameters=pipes.CfnPipe.PipeTargetParametersProperty(
                #     input_template=" { \"body\": <$.body>, \"attributes\": <$.attributes> } "
                # ),
                log_configuration=pipes.CfnPipe.PipeLogConfigurationProperty(
                    cloudwatch_logs_log_destination=pipes.CfnPipe.CloudwatchLogsLogDestinationProperty(
                        log_group_arn=imt_pipes_imtmt_pre_log_group.log_group_arn
                    ),
                    level="TRACE" # TRACE, INFO, ERROR
                )
        )

        # Create EventBridge rule that takes IMTMT  messages from the bus and sends them to the IMTMT PRE queue

        imt_mt_rule = events.Rule(self, "imt_mt_rule",
            event_bus = imt_bus,
            event_pattern=events.EventPattern(
                account=[Stack.of(self).account],
                source=["Pipe IMTMT_PRE_DEV"],
            )
        )

        # Create rule target for SQS
        imt_mt_rule.add_target(targets.SqsQueue(imt_mt_pre_queue))


        imt_imtmt_pipe_role = iam.Role(
            self,"imt_imtmt_pipe_role",
            assumed_by=iam.ServicePrincipal("pipes.amazonaws.com")
        )
        
        # Add permissions to receive and delete messages from the IMTMO Queue
        imt_imtmt_pipe_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=[ImtQueueImtmtArn.value_as_string, imt_mt_pre_queue.queue_arn],
            actions=[
                "sqs:ReceiveMessage",
                "sqs:DeleteMessage",
                "sqs:GetQueueAttributes"
            ]
        ))

 
         # Create the log group
        imt_pipes_imtmt_pre_log_group = logs.LogGroup(self, "/aws/vendedlogs/pipes/IMTMT_DEV")

        # Create pipe that takes data from DynamoDB and delivers it to imt-bus
        imt_imtmt_pipe = pipes.CfnPipe(self, "imt_imtmt_pipe",
                name="IMTMT_DEV",
                role_arn=imt_imtmt_pipe_role.role_arn,
                source=imt_mt_pre_queue.queue_arn,
                source_parameters=pipes.CfnPipe.PipeSourceParametersProperty(
                    sqs_queue_parameters=pipes.CfnPipe.PipeSourceSqsQueueParametersProperty(
                        batch_size=1
                    )
                ),
                target=ImtQueueImtmtArn.value_as_string,
                target_parameters=pipes.CfnPipe.PipeTargetParametersProperty(
                    input_template="{ \"cmid\": <$.body.detail.dynamodb.Keys.cmid.S>, \"topicId\": " + ImtTopicId.value_as_string+ ", \"payload\": <$.body.detail.dynamodb.NewImage.message.M.payload.S>, \"requestReference\": <$.body.detail.dynamodb.NewImage.message.M.requestReference.S>, \"ringStyle\": <$.body.detail.dynamodb.NewImage.message.M.ringStyle.S> }",
                    sqs_queue_parameters=pipes.CfnPipe.PipeTargetSqsQueueParametersProperty(
                        message_deduplication_id="$.body.detail.dynamodb.NewImage.message.M.requestReference.S",
                        message_group_id="$.body.detail.dynamodb.NewImage.message.M.requestReference.S"
                    )
                ),
                log_configuration=pipes.CfnPipe.PipeLogConfigurationProperty(
                    cloudwatch_logs_log_destination=pipes.CfnPipe.CloudwatchLogsLogDestinationProperty(
                        log_group_arn=imt_pipes_imtmt_pre_log_group.log_group_arn
                    ),
                    level="TRACE" # TRACE, INFO, ERROR
                )
        )

        imt_imtmt_rule = iot.TopicRule(self, "imt_imtmt_rule",
            topic_rule_name="imt_imtmt_rule", 
            description="takes messages from IoT Core and sends them to DynamoDB", 
            sql=iot.IotSql.from_string_as_ver20160323('''SELECT
    topic(2) AS cmid,
    timestamp() AS ts,
    topicId AS message.topicId,
    requestReference AS message.requestReference,
    ringStyle AS message.ringStyle,
    payload AS message.payload,
FROM
    \''''+ImtIoTPrefix.value_as_string+'''/+/mt\' 
'''),
            actions=[actions.DynamoDBv2PutItemAction(imt_mt_table2)]
        )

    ########################################################################################################
    ##### STATUS START #####################################################################################
    ########################################################################################################


        # Create DynamoDB table to store MT messages
        imt_mt_table = dynamodb.Table(self, "imt_mt_table",
            partition_key=dynamodb.Attribute(name="requestReference", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="ts", type=dynamodb.AttributeType.STRING)
        )

        # Create a pipe to connect IMTSTATUS Q with IMT bus
        # Create role 
        imt_pipes_imtstatus_role = iam.Role(
            self,"imt_pipes_imtstatus_role",
            assumed_by=iam.ServicePrincipal("pipes.amazonaws.com")
        )
        # Add permissions to publish to the event bus
        imt_pipes_imtstatus_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=[imt_bus.event_bus_arn],
            actions=[
                "events:PutEvents"
            ]
        ))
        # Add permissions to receive and delete messages from the IMTSTATUS Queue
        imt_pipes_imtstatus_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=[ImtQueueImtStatusArn.value_as_string],
            actions=[
                "sqs:ReceiveMessage",
                "sqs:DeleteMessage",
                "sqs:GetQueueAttributes"
            ]
        ))
        # Create the pipe 
        imt_imtstatus_pipe = pipes.CfnPipe(self, "imt_imtstatus_pipe",
                role_arn=imt_pipes_imtstatus_role.role_arn,
                source=ImtQueueImtStatusArn.value_as_string,
                source_parameters=pipes.CfnPipe.PipeSourceParametersProperty(
                    sqs_queue_parameters=pipes.CfnPipe.PipeSourceSqsQueueParametersProperty(
                        batch_size=1
                    )
                ),
                target=imt_bus.event_bus_arn,
                target_parameters=pipes.CfnPipe.PipeTargetParametersProperty(
                    input_template=" { \"body\": <$.body>, \"attributes\": <$.attributes> } "
                ),
                name="IMTSTATUS_DEV",
                log_configuration=pipes.CfnPipe.PipeLogConfigurationProperty(
                    cloudwatch_logs_log_destination=pipes.CfnPipe.CloudwatchLogsLogDestinationProperty(
                        log_group_arn=imt_pipes_imtmt_pre_log_group.log_group_arn
                    ),
                    level="TRACE" # TRACE, INFO, ERROR
                )
        )

        # Create API GWs to glue EB Rules with IoT & DynamoDB

        # Create role for API gateway to use when publishing to iot
        imt_iot_status_api_role = iam.Role(
            self,"imt_iot_status_api_role",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com")
        )
        imt_iot_status_api_role_resource = "arn:aws:iot:" + IoTRegion.value_as_string + ":" + IoTAccount.value_as_string + ":topic/" + ImtIoTPrefix.value_as_string + "/*/status/*"
        imt_iot_status_api_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=[imt_iot_status_api_role_resource],
            actions=[
                "iot:Publish"
            ]
        ))
        # Create integration for API gateway to publish to IoT
        imt_mo_message_integration_request_iot_core = apigw.AwsIntegration(
            service="iotdata",
            integration_http_method="POST",
            path="topics/"+ImtIoTPrefix.value_as_string+"/{cmid}/status/{requestReference}?qos=1", # {cmid} is a path parameter
            subdomain=IoTSubDomain.value_as_string,
            region=IoTRegion.value_as_string,
            options=apigw.IntegrationOptions(
                request_parameters={"integration.request.path.cmid": "method.request.path.cmid", "integration.request.path.requestReference": "method.request.path.requestReference"  },
                integration_responses=[
                    apigw.IntegrationResponse(
                        status_code="200",
                        response_templates={"application/json": ""}
                    )
                ],
                credentials_role=imt_iot_status_api_role
                
            )
        )
    
        # Create IoT api gateway
        imt_iot_status_api = apigw.RestApi(self, "imt_iot_status_api")

        # Add /{cmid} path/resource
        imt_iot_status_api_resource = imt_iot_status_api.root.add_resource("{cmid}").add_resource("{requestReference}")
        # Add method to API gateway
        imt_iot_status_api_resource.add_method(
            "POST", 
            imt_mo_message_integration_request_iot_core, 
            method_responses=[apigw.MethodResponse(status_code="200")],
            request_parameters={"method.request.path.cmid": False, "method.request.path.requestReference": False},
            authorization_type=apigw.AuthorizationType.IAM
        )


        # Create role for API gateway to use when publishing to DynamoDB
        imt_dynamodb_status_api_api_role = iam.Role(
            self,"imt_dynamodb_status_api_api_role",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com")
        )
        imt_dynamodb_status_api_api_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=[imt_mt_table.table_arn],
            actions=[
                "dynamodb:PutItem"
            ]
        ))
 
        imt_dynamodb_status_request_template = """
#set($messageId = $input.path('$.detail.body.mtMessageStatus.messageId'))
{ 
    "TableName": \""""+ imt_mt_table.table_name + """\",
    "Item": {
	    "requestReference": {
            "S": "$input.path('$.detail.body.mtMessageStatus.requestReference')"
            },
        "ts": {
            "N": "$input.path('$.detail.attributes.SentTimestamp')"
            },
        "detail": {
            "M": {
			    "body": {
            		"M": {
                        "mtMessageStatus": {
                            "M" : {
                                "cmid": {
                                    "S": "$input.path('$.detail.body.mtMessageStatus.cmid')"
                                },
                                "deliveryStatus": {
                                    "S": "$input.path('$.detail.body.mtMessageStatus.deliveryStatus')"
                                },
                                
                                #if($messageId != '')
                                "messageId": {
                                    "N": "$messageId"
                                },
                                #end
                                "messagePending": {
                                    "BOOL": "$input.path('$.detail.body.mtMessageStatus.messagePending')"
                                },
                                "requestReference": {
                                    "S": "$input.path('$.detail.body.mtMessageStatus.requestReference')"
                                },
                                "topicId": {
                                    "N": "$input.path('$.detail.body.mtMessageStatus.topicId')"
                                },
                                "version": {
                                    "S": "$input.path('$.detail.body.mtMessageStatus.version')"
                                }
                            }
                        }
                    }
                },
                "attributes": {
                    "M" : {
                        "ApproximateReceiveCount": {
                            "S": "$input.path('$.detail.attributes.ApproximateReceiveCount')"
                        },
                        "SentTimestamp": {
                            "S": "$input.path('$.detail.attributes.SentTimestamp')"
                        },
                        "SequenceNumber": {
                            "S": "$input.path('$.detail.attributes.SequenceNumber')"
                        },
                        "MessageGroupId": {
                            "S": "$input.path('$.detail.attributes.MessageGroupId')"
                        },
                        "SenderId": {
                            "S": "$input.path('$.detail.attributes.SenderId')"
                        },
                        "MessageDeduplicationId": {
                            "S": "$input.path('$.detail.attributes.MessageDeduplicationId')"
                        },
                        "ApproximateFirstReceiveTimestamp": {
                            "S": "$input.path('$.detail.attributes.ApproximateFirstReceiveTimestamp')"
                        }
                    }       
                }
            }
        }
    }
}

"""

        # Create DynamoDB api gateway
        imt_dynamodb_status_api = apigw.RestApi(self, "imt_status_dynamodb_api")

        # Add /{cmid} path/resource
        imt_dynamodb_status_api_resource = imt_dynamodb_status_api.root.add_resource("{cmid}").add_resource("{requestReference}")
        
        # Add method to API gateway
        imt_dynamodb_status_api_resource.add_method(
            "POST", 
            imt_mo_message_integration_dynamodb, 
            method_responses=[apigw.MethodResponse(status_code="200")],
            request_parameters={"method.request.path.cmid": False},
            authorization_type=apigw.AuthorizationType.IAM
        )

        # Create rule to capture messages coming fom imt_mo pipe
        imt_status_rule = events.Rule(self, "imt_status_rule",
            event_bus = imt_bus,
            event_pattern=events.EventPattern(
                account=[Stack.of(self).account],
                source=["Pipe IMTSTATUS_DEV"],
            )
        )
        # Create rule target for Iot
        imt_status_rule.add_target(
            targets.ApiGateway(imt_iot_status_api,
                path="/*/*",
                method="POST",
                stage="prod",
                path_parameter_values=["$.detail.body.cmid", "$.detail.body.requestReference"]
        ))
        

        # Create rule target for DynamoDB
        imt_status_rule.add_target(
            targets.ApiGateway(imt_dynamodb_status_api,
                path="/*/*",
                method="POST",
                stage="prod",
                path_parameter_values=["$.detail.body.cmid", "$.detail.body.requestReference"]
        ))