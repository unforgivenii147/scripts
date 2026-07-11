import builtins
import os
import os.path
import subprocess
import sys
import typing
import xonsh.dirstack  # type: ignore # pylint: disable=import-error
import xonsh.environ  # type: ignore # pylint: disable=import-error


def __zoxide_bin() -> str:
    """Finds and returns the location of the zoxide binary."""
    zoxide = typing.cast(str, xonsh.environ.locate_binary("zoxide"))
    if zoxide is None:
        zoxide = "zoxide"
    return zoxide


def __zoxide_env() -> dict[str, str]:
    """Returns the current environment."""
    return builtins.__xonsh__.env.detype()  # type: ignore  # pylint:disable=no-member


def __zoxide_pwd() -> str:
    """pwd based on the value of _ZO_RESOLVE_SYMLINKS."""
    pwd = __zoxide_env().get("PWD")
    if pwd is None:
        raise RuntimeError("$PWD not found")
    pwd = os.getcwd()
    return pwd


def __zoxide_cd(path: str | bytes | None = None) -> None:
    """cd + custom logic based on the value of _ZO_ECHO."""
    if path is None:
        args = []
    elif isinstance(path, bytes):
        args = [path.decode("utf-8")]
    else:
        args = [path]
    _, exc, _ = xonsh.dirstack.cd(args)
    if exc is not None:
        raise RuntimeError(exc)
    print(__zoxide_pwd())


class ZoxideSilentException(Exception):
    """Exit without complaining."""


def __zoxide_errhandler(
    func: typing.Callable[[list[str]], None],
) -> typing.Callable[[list[str]], int]:
    """Print exception and exit with error code 1."""

    def wrapper(args: list[str]) -> int:
        try:
            func(args)
            return 0
        except ZoxideSilentException:
            return 1
        except Exception as exc:
            print(f"zoxide: {exc}", file=sys.stderr)
            return 1

    return wrapper


if "__zoxide_hook" not in globals():

    @builtins.events.on_chdir  # type: ignore  # pylint:disable=no-member
    @builtins.events.on_post_prompt  # type: ignore  # pylint:disable=no-member
    def __zoxide_hook(**_kwargs: typing.Any) -> None:
        """Hook to add new entries to the database."""
        pwd = __zoxide_pwd()
        zoxide = __zoxide_bin()
        subprocess.run(
            [zoxide, "add", "--", pwd],
            check=False,
            env=__zoxide_env(),
        )


@__zoxide_errhandler
def __zoxide_z(args: list[str]) -> None:
    """Jump to a directory using only keywords."""
    if args == []:
        __zoxide_cd()
    elif args == ["-"]:
        __zoxide_cd("-")
    elif len(args) == 1 and os.path.isdir(args[0]):
        __zoxide_cd(args[0])
    else:
        try:
            zoxide = __zoxide_bin()
            cmd = subprocess.run(
                [zoxide, "query", "--exclude", __zoxide_pwd(), "--"] + args,
                check=True,
                env=__zoxide_env(),
                stdout=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as exc:
            raise ZoxideSilentException() from exc
        result = cmd.stdout[:-1]
        __zoxide_cd(result)


@__zoxide_errhandler
def __zoxide_zi(args: list[str]) -> None:
    """Jump to a directory using interactive search."""
    try:
        zoxide = __zoxide_bin()
        cmd = subprocess.run(
            [zoxide, "query", "-i", "--"] + args,
            check=True,
            env=__zoxide_env(),
            stdout=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        raise ZoxideSilentException() from exc
    result = cmd.stdout[:-1]
    __zoxide_cd(result)


builtins.aliases[""] = __zoxide_z  # type: ignore  # pylint:disable=no-member
builtins.aliases["i"] = __zoxide_zi  # type: ignore  # pylint:disable=no-member
