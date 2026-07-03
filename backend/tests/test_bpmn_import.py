"""Tests fuer den BPMN-XML-Subset-Parser und den /admin/definitions/upload-bpmn-Endpoint."""
from __future__ import annotations

import json
import textwrap

import pytest

from app.admin.bpmn import BpmnImportError, parse_bpmn_to_graph

BPMN_NS = 'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"'
CAMUNDA_NS = 'xmlns:camunda="http://camunda.org/schema/1.0/bpmn"'


def _wrap(process_inner: str) -> bytes:
    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<bpmn:definitions {BPMN_NS} {CAMUNDA_NS}>\n'
        f'  <bpmn:process id="proc_1" isExecutable="true">\n'
        f'{process_inner}\n'
        f'  </bpmn:process>\n'
        f'</bpmn:definitions>\n'
    )
    return xml.encode("utf-8")


def test_parse_minimal_linear_diagram():
    xml = _wrap('''
      <bpmn:startEvent id="StartEvent_1" />
      <bpmn:userTask id="Task_1" name="Pruefung" camunda:assignee="Fachbereichsleiter" />
      <bpmn:endEvent id="EndEvent_1" />
      <bpmn:sequenceFlow id="f1" sourceRef="StartEvent_1" targetRef="Task_1" />
      <bpmn:sequenceFlow id="f2" sourceRef="Task_1" targetRef="EndEvent_1" />
    ''')
    g = parse_bpmn_to_graph(xml)
    types = {n["id"]: n["type"] for n in g["nodes"]}
    assert types == {"StartEvent_1": "start", "Task_1": "user_task", "EndEvent_1": "end"}
    task = next(n for n in g["nodes"] if n["id"] == "Task_1")
    assert task["rolle"] == "Fachbereichsleiter"
    assert task["label"] == "Pruefung"


def test_parallel_gateway_classified_as_split_and_join():
    xml = _wrap('''
      <bpmn:startEvent id="s" />
      <bpmn:parallelGateway id="split" />
      <bpmn:userTask id="a" name="A" camunda:assignee="Compliance" />
      <bpmn:userTask id="b" name="B" camunda:assignee="Risikomanagement" />
      <bpmn:parallelGateway id="join" />
      <bpmn:userTask id="v" name="V" camunda:assignee="Vorstand" />
      <bpmn:endEvent id="e" />
      <bpmn:sequenceFlow id="f1" sourceRef="s"     targetRef="split" />
      <bpmn:sequenceFlow id="f2" sourceRef="split" targetRef="a" />
      <bpmn:sequenceFlow id="f3" sourceRef="split" targetRef="b" />
      <bpmn:sequenceFlow id="f4" sourceRef="a"     targetRef="join" />
      <bpmn:sequenceFlow id="f5" sourceRef="b"     targetRef="join" />
      <bpmn:sequenceFlow id="f6" sourceRef="join"  targetRef="v" />
      <bpmn:sequenceFlow id="f7" sourceRef="v"     targetRef="e" />
    ''')
    g = parse_bpmn_to_graph(xml)
    types = {n["id"]: n["type"] for n in g["nodes"]}
    assert types["split"] == "parallel_split"
    assert types["join"] == "parallel_join"


def test_user_task_without_role_rejected():
    xml = _wrap('''
      <bpmn:startEvent id="s" />
      <bpmn:userTask id="t" name="ohne Rolle" />
      <bpmn:endEvent id="e" />
      <bpmn:sequenceFlow id="f1" sourceRef="s" targetRef="t" />
      <bpmn:sequenceFlow id="f2" sourceRef="t" targetRef="e" />
    ''')
    with pytest.raises(BpmnImportError, match="ohne Rolle"):
        parse_bpmn_to_graph(xml)


def test_role_via_potential_owner():
    xml = _wrap('''
      <bpmn:startEvent id="s" />
      <bpmn:userTask id="t" name="x">
        <bpmn:potentialOwner>
          <bpmn:resourceAssignmentExpression>
            <bpmn:formalExpression>Compliance</bpmn:formalExpression>
          </bpmn:resourceAssignmentExpression>
        </bpmn:potentialOwner>
      </bpmn:userTask>
      <bpmn:endEvent id="e" />
      <bpmn:sequenceFlow id="f1" sourceRef="s" targetRef="t" />
      <bpmn:sequenceFlow id="f2" sourceRef="t" targetRef="e" />
    ''')
    g = parse_bpmn_to_graph(xml)
    task = next(n for n in g["nodes"] if n["id"] == "t")
    assert task["rolle"] == "Compliance"


def test_role_via_documentation_prefix():
    xml = _wrap('''
      <bpmn:startEvent id="s" />
      <bpmn:userTask id="t" name="x">
        <bpmn:documentation>rolle: Vorstand</bpmn:documentation>
      </bpmn:userTask>
      <bpmn:endEvent id="e" />
      <bpmn:sequenceFlow id="f1" sourceRef="s" targetRef="t" />
      <bpmn:sequenceFlow id="f2" sourceRef="t" targetRef="e" />
    ''')
    g = parse_bpmn_to_graph(xml)
    task = next(n for n in g["nodes"] if n["id"] == "t")
    assert task["rolle"] == "Vorstand"


def test_service_task_rejected():
    xml = _wrap('''
      <bpmn:startEvent id="s" />
      <bpmn:serviceTask id="svc" name="echo" />
      <bpmn:endEvent id="e" />
      <bpmn:sequenceFlow id="f1" sourceRef="s" targetRef="svc" />
      <bpmn:sequenceFlow id="f2" sourceRef="svc" targetRef="e" />
    ''')
    with pytest.raises(BpmnImportError, match="Unerlaubtes BPMN-Element"):
        parse_bpmn_to_graph(xml)


def test_exclusive_gateway_rejected():
    xml = _wrap('''
      <bpmn:startEvent id="s" />
      <bpmn:exclusiveGateway id="g" />
      <bpmn:endEvent id="e" />
      <bpmn:sequenceFlow id="f1" sourceRef="s" targetRef="g" />
      <bpmn:sequenceFlow id="f2" sourceRef="g" targetRef="e" />
    ''')
    with pytest.raises(BpmnImportError, match="Unerlaubtes BPMN-Element"):
        parse_bpmn_to_graph(xml)


def test_invalid_xml_rejected():
    with pytest.raises(BpmnImportError, match="kann nicht geparst"):
        parse_bpmn_to_graph(b"<not really xml>")


def test_no_process_element_rejected():
    xml = b'<?xml version="1.0"?><bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" />'
    with pytest.raises(BpmnImportError, match="Kein bpmn:process"):
        parse_bpmn_to_graph(xml)


def test_upload_bpmn_endpoint_creates_draft(client, admin_auth):
    """End-to-End: BPMN hochladen -> Draft-Definition entsteht."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["a"],
        "properties": {"a": {"type": "string"}},
    }
    ui = {"type": "VerticalLayout", "elements": []}
    bpmn = _wrap('''
      <bpmn:startEvent id="s" />
      <bpmn:userTask id="t" name="Pruefung" camunda:assignee="Fachbereichsleiter" />
      <bpmn:endEvent id="e" />
      <bpmn:sequenceFlow id="f1" sourceRef="s" targetRef="t" />
      <bpmn:sequenceFlow id="f2" sourceRef="t" targetRef="e" />
    ''')
    files = {
        "json_schema": ("s.json", json.dumps(schema).encode(), "application/json"),
        "ui_schema":   ("u.json", json.dumps(ui).encode(),     "application/json"),
        "bpmn_xml":    ("p.bpmn", bpmn, "application/xml"),
    }
    data = {"typ": "BPMN_Test", "version": "1.0.0", "titel": "BPMN-Import-Test"}
    r = client.post("/admin/definitions/upload-bpmn", data=data, files=files, headers=admin_auth)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "draft"
    nids = {n["id"] for n in body["workflow_graph"]["nodes"]}
    assert {"s", "t", "e"} == nids
