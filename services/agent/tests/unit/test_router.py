from agent.router import RouterInput, decide_route


def base(**kw):
    d = {
        "needs_network": False,
        "needs_cloud_llm": False,
        "network_up": True,
        "profile": "hosted",
        "cloud_enabled": True,
    }
    d.update(kw)
    return RouterInput(**d)


def test_local_task_runs_without_approval_or_network_check():
    assert decide_route(base(network_up=False)) == "run_now"


def test_cloud_task_asks_approval_when_online():
    assert decide_route(base(needs_cloud_llm=True, needs_network=True)) == "ask_cloud_approval"


def test_cloud_task_approved_for_session_runs_now():
    assert (
        decide_route(base(needs_cloud_llm=True, needs_network=True, approved_for_session=True))
        == "run_now"
    )


def test_offline_cloud_task_is_queued_and_user_told():
    assert (
        decide_route(base(needs_cloud_llm=True, needs_network=True, network_up=False))
        == "queue_and_tell"
    )


def test_offline_send_is_queued():
    assert decide_route(base(needs_network=True, network_up=False)) == "queue_and_tell"


def test_admin_disabled_cloud_never_routes_to_cloud():
    assert (
        decide_route(base(needs_cloud_llm=True, needs_network=True, cloud_enabled=False))
        == "unavailable"
    )


def test_local_profile_never_routes_to_cloud():
    assert (
        decide_route(base(needs_cloud_llm=True, needs_network=True, profile="local"))
        == "use_local_model"
    )
