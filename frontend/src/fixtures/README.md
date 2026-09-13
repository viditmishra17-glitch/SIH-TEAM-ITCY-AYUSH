# Frontend fixtures

`sample-case.json` is a real `GET /cases/{case_id}` response, captured from the
seeded TV-0002 case.

Build Manual section 9 ("frontend fixture strategy") asks the UI to render the
final result shape before the backend is finished. Keep this file in step with
the frozen contract in `engine/schemas.py` and use it to develop screens with
no API running:

```js
import sample from './fixtures/sample-case.json'
// then render <CasePage/> against `sample` instead of calling getCase()
```

Regenerate after any contract change, from the backend/ directory:

```
python -c "from fastapi.testclient import TestClient; from app.main import app; import json; print(json.dumps(TestClient(app).get('/cases/TV-0002').json(), indent=2))" > ../frontend/src/fixtures/sample-case.json
```
