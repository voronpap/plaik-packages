from plaik_sdk import ExtensionRuntime


def register(runtime: ExtensionRuntime) -> None:
    if runtime.package_id != "search":
        raise ValueError("runtime package id does not match this package")

    def handle_reindex(context) -> None:
        del context

    runtime.jobs.register("search.reindex", handle_reindex)
