"""Pure routing decision. See docs/TECH_SPEC.md section 6. No I/O here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Route = Literal[
    "run_now",  # runs on the device, or is a direct provider call (mail), no approval needed
    "use_local_model",  # Local profile: the on-device model does the language work
    "ask_cloud_approval",
    "queue_and_tell",
    "unavailable",  # cloud disabled by admin and no local model
]


@dataclass(frozen=True)
class RouterInput:
    needs_network: bool
    needs_cloud_llm: bool
    network_up: bool
    profile: Literal["hosted", "local"]
    cloud_enabled: bool  # admin setting
    approved_for_session: bool = False


def decide_route(r: RouterInput) -> Route:
    # Nothing in the task needs the cloud or the network: run now.
    if not r.needs_network and not r.needs_cloud_llm:
        return "run_now"
    # Local profile and admin-disabled cloud never route to the cloud.
    if r.needs_cloud_llm and (r.profile == "local" or not r.cloud_enabled):
        return "use_local_model" if r.profile == "local" else "unavailable"
    # Needs the internet but it is down: queue and tell the user once.
    if not r.network_up:
        return "queue_and_tell"
    # Online: cloud steps need approval (unless approved once per session).
    if r.needs_cloud_llm and not r.approved_for_session:
        return "ask_cloud_approval"
    return "run_now"
