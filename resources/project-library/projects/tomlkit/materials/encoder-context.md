# One bounded export

In a single-threaded export, render_artifact(path) returns a TOML document containing only artifact = the string representation of a supplied pathlib.PurePath. Synthetic example: PurePosixPath("build/报告.toml"). Do not read the path. Preserve all pre-existing encoder objects in order. Register only your own bounded encoder and remove only it in finally, including failure on unsupported object(). Unsupported values must raise ConvertError, not silently stringify. Registration is process-global; cleanup is not concurrent isolation.
