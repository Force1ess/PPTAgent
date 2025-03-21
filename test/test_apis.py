from pptagent.apis import CodeExecutor, API_TYPES


def test_api_docs():
    executor = CodeExecutor(3)
    docs = executor.get_apis_docs(API_TYPES.Agent.value)
    assert len(docs) > 0
