"""Deliberately partial pinned-field Protobuf *test fixture*, NOT official SDK.

NVP installed runtime must use exact Lu-generated workspace.proto and native
OS-attested transport. The fixture matches the field numbers needed for R2.
"""
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory


def _class_map(package, entries):
    file = descriptor_pb2.FileDescriptorProto()
    file.name = package.replace('.', '/') + '/nvp_r2_test_projection.proto'
    file.package = package
    file.syntax = 'proto3'
    names = {}
    K = {'string': 9, 'bytes': 12, 'uint32': 13, 'uint64': 4, 'bool': 8, 'enum': 5}
    for name, fields, oneofs in entries:
        msg = file.message_type.add(); msg.name = name
        for oneof in oneofs:
            msg.oneof_decl.add().name = oneof
        for record in fields:
            field_name, index, kind = record[:3]
            f = msg.field.add(); f.name = field_name; f.number = index
            f.label = 3 if len(record) > 3 and record[3] == 'repeated' else 1
            if kind.startswith('message:'):
                f.type = 11
                f.type_name = '.' + package + '.' + kind.split(':')[1]
            else:
                f.type = K[kind]
            if len(record) > 4:
                f.oneof_index = record[4]
        names[name] = msg
    pool = descriptor_pool.DescriptorPool()
    pool.AddSerializedFile(file.SerializeToString())
    return {name: message_factory.GetMessageClass(pool.FindMessageTypeByName(package + '.' + name))
            for name in names}


def lu_fixture():
    return _class_map('lu.workspace.v0', [
      ('OriginRefs', [('workspace_ref',1,'string'),('conversation_ref',2,'string'),
          ('user_turn_ref',3,'string'),('task_ref',4,'string'),('operation_ref',5,'string')], []),
      ('TypedValue', [('type_url',1,'string'),('encoded_message',2,'bytes')], []),
      ('ObjectRef', [('owner_module_id',1,'string'),('object_ref',2,'string'),
          ('sha256',3,'bytes'),('size_bytes',4,'uint64'),('expiry_unix_ms',5,'uint64')], []),
      ('CapabilityInvoke', [('origin',1,'message:OriginRefs'),('capability_id',2,'string'),
          ('capability_version',3,'uint32'),('input',4,'message:TypedValue'),
          ('input_refs',5,'message:ObjectRef','repeated'),('deadline_unix_ms',6,'uint64')], []),
      ('OperationProgress', [('stage_code',1,'string')], []),
      ('OperationReceipt', [('operation_ref',1,'string'),('state',2,'enum'),
          ('reason_code',3,'string'),('output',4,'message:TypedValue'),
          ('durable_receipt_sha256',5,'bytes'),('output_refs',6,'message:ObjectRef','repeated')], []),
      ('OperationEvent', [('operation_ref',1,'string'),
          ('progress',2,'message:OperationProgress',None,0),
          ('terminal',3,'message:OperationReceipt',None,0)], ['data']),
      ('CancelOperation', [('operation_ref',1,'string'),('reason_code',2,'string')], []),
      ('CancelAcknowledged', [('operation_ref',1,'string'),('signal_recorded',2,'bool')], []),
      ('ReconcileOperation', [('operation_ref',1,'string'),('expected_origin',2,'message:OriginRefs')], []),
      ('ReconciledOperation', [('observed',1,'message:OperationReceipt'),('evidence_available',2,'bool')], []),
      ('ProtocolFailure', [('code',1,'string'),('retryable',2,'bool'),
          ('outcome_uncertain',3,'bool'),('explanation',4,'string')], []),
      ('StreamCredit', [('operation_ref',1,'string'),('acknowledged_sequence',2,'uint64'),
          ('additional_events',3,'uint32')], []),
      ('WorkspaceFrame', [('protocol_major',1,'uint32'),('protocol_minor',2,'uint32'),
          ('request_id',3,'string'),('session_ref',4,'string'),('sequence',5,'uint64'),
          ('invoke',15,'message:CapabilityInvoke',None,0),
          ('operation_event',16,'message:OperationEvent',None,0),
          ('cancel',17,'message:CancelOperation',None,0),
          ('cancel_ack',18,'message:CancelAcknowledged',None,0),
          ('reconcile',19,'message:ReconcileOperation',None,0),
          ('reconciled',20,'message:ReconciledOperation',None,0),
          ('stream_credit',29,'message:StreamCredit',None,0),
          ('failure',30,'message:ProtocolFailure',None,0)], ['body']),
    ])


def domain_fixture():
    caps = ['ProjectReadRequest','SceneReadRequest','StoryProposalRequest',
            'ProjectCommitRequest','RenderShotRequest','PictureReviewReadRequest',
            'PictureReviewDecisionRequest','FilmExportRequest']
    return _class_map('nvp.film.v1', [(name,[('project_ref',1,'string')], []) for name in caps])
