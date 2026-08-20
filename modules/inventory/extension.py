from plaik_sdk import ExtensionRuntime


def register(runtime: ExtensionRuntime) -> None:
    if runtime.package_id != "inventory":
        raise ValueError("runtime package id does not match this package")

    def handle_sync(context) -> None:
        del context

    runtime.jobs.register("inventory.sync", handle_sync)
