"""Export/check the actual API contract without connecting to runtime services."""
import json
import sys
from app.config import ROOT
from app.main import create_app

target=ROOT/'contracts/qualification-openapi.json'
source=json.dumps(create_app().openapi(),indent=2,sort_keys=True)+'\n'
if '--check' in sys.argv:
    assert target.read_text()==source, 'OpenAPI changed: regenerate the browser contract.'
    print('OpenAPI matches the implemented API.')
else:
    target.parent.mkdir(exist_ok=True)
    target.write_text(source)
