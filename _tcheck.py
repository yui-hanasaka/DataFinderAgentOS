import tornado.template
import os

td = os.path.join(os.path.dirname(os.path.abspath(".")), "app", "templates")
loader = tornado.template.Loader(td)

# Verify model_test.html with simulated context
t = loader.load("admin/model_test.html")
try:
    result = t.generate(
        title="Test",
        model={
            "id": 1,
            "name": "gpt-4",
            "model_id": "gpt-4-turbo",
            "temperature": 0.7,
            "max_tokens": 4096,
            "system_prompt": "You are helpful.",
        },
        usage={"calls": 0, "prompt": 0, "completion": 0, "total": 0},
    )
    print("model_test.html: OK, generated", len(result), "bytes")
except Exception as e:
    print(f"model_test.html: FAIL - {e}")

# Verify settings.html with simulated context
t = loader.load("admin/settings.html")
try:
    result = t.generate(
        title="Settings",
        settings={},
        msg="",
        request=tornado.httputil.HTTPServerRequest(uri="/admin/settings"),
    )
    print("settings.html: OK, generated", len(result), "bytes")
except Exception as e:
    print(f"settings.html: FAIL - {e}")

# Verify login.html
t = loader.load("web/login.html")
try:
    result = t.generate(title="Login", error=None)
    print("login.html: OK, generated", len(result), "bytes")
except Exception as e:
    print(f"login.html: FAIL - {e}")

# Verify landing.html
t = loader.load("web/landing.html")
try:
    result = t.generate(title="Landing")
    print("landing.html: OK, generated", len(result), "bytes")
except Exception as e:
    print(f"landing.html: FAIL - {e}")
