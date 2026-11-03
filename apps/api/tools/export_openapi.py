"""Export/check the actual API contract without connecting to runtime services."""
import json
import sys
from app.config import ROOT
from app.main import create_app
from app.tenders.screening import ScreeningArtifact

screening_schema={**ScreeningArtifact.model_json_schema(),
    '$id':'urn:tender-intelligence:m1:screening:v1','$schema':'https://json-schema.org/draft/2020-12/schema'}
for path,schema in [('contracts/qualification-openapi.json',create_app().openapi()),
                    ('contracts/qualification/screening.schema.json',screening_schema)]:
    target=ROOT/path
    source=json.dumps(schema,indent=2,sort_keys=True)+'\n'
    if '--check' in sys.argv:
        assert target.read_text()==source, f'{path} changed: regenerate the contracts.'
    else:
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(source)
if '--check' in sys.argv: print('OpenAPI and screening artifact schema match the implementation.')
