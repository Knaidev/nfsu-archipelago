from worlds.LauncherComponents import Component, Type, components, launch

from .items import GAME_NAME


def run_client(*args: str) -> None:
    from .client.context import launch as launch_nfsu_client
    launch(launch_nfsu_client, name="NFSU Client", args=args)


components.append(
    Component(
        "NFSU Client",
        func=run_client,
        game_name=GAME_NAME,
        component_type=Type.CLIENT,
        supports_uri=True,
        description="Connects Need for Speed: Underground (PCSX2 with PINE) to Archipelago.",
    )
)
