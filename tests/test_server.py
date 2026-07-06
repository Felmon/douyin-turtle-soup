"""集成测试 — 服务器启动、健康检查、Admin API 认证、WebSocket"""


def test_health_check(client):
    """公开的健康检查端点应返回 200"""
    resp = client.get("/health")
    assert resp.status_code == 200


def test_admin_api_no_auth(client):
    """无 token 访问 admin API 应返回 401"""
    resp = client.post("/api/admin/soups/add", json={"content": "test"})
    assert resp.status_code == 401


def test_admin_api_invalid_token(client):
    """错误 token 访问 admin API 应返回 401"""
    resp = client.get(
        "/api/admin/soups",
        headers={"Authorization": "Bearer invalid_token_12345"},
    )
    assert resp.status_code == 401


def test_admin_api_valid_token(client, auth_headers):
    """正确 token 可访问 admin API"""
    resp = client.get(
        "/api/admin/soups",
        headers=auth_headers,
    )
    # 即使数据为空也是 200（不是 401）
    assert resp.status_code == 200


def test_public_api_no_auth_needed(client):
    """公开 API 不应被认证拦截"""
    resp = client.get("/api/game/current")
    # 公开 API 应返回 200 或 4xx（非 401），取决于游戏状态
    assert resp.status_code != 401


def test_websocket_connect(client):
    """WebSocket 连接应成功建立"""
    with client.websocket_connect("/ws") as ws:
        data = ws.receive_json()
        assert "type" in data
