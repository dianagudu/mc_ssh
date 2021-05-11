#!/usr/bin/env python3

from functools import wraps
import click
from click_option_group import optgroup, MutuallyExclusiveOptionGroup

from .ssh_service import ssh_exec, ssh_interactive, scp_put, scp_get, SSH_PORT
from .utils import validate_insecure_flip2verify, validate_scp_source, validate_scp_target
from .utils import init_endpoint, init_token, init_user, str_init_token


def common_options(func):
    @click.option("--mc-endpoint",
                  help="motley_cue API endpoint, default URLs: https://HOSTNAME, http://HOSTNAME:8080")
    @click.option("--insecure", "verify", is_flag=True, default=False,
                  callback=validate_insecure_flip2verify,
                  help="ignore verifying the SSL certificate for motley_cue endpoint, NOT RECOMMENDED")
    @optgroup.group("Access Token sources",
                    help="the sources for retrieving the access token, odered by priority",
                    cls=MutuallyExclusiveOptionGroup)
    @optgroup.option("--token",
                     envvar=["ACCESS_TOKEN", "OIDC",
                             "OS_ACCESS_TOKEN", "OIDC_ACCESS_TOKEN",
                             "WATTS_TOKEN", "WATTSON_TOKEN"],
                     show_envvar=True,
                     help="pass token directly, env variables are checked in given order")
    @optgroup.option("--oa-account",
                     envvar=["OIDC_AGENT_ACCOUNT"], show_envvar=True,
                     help="name of configured account in oidc-agent")
    @optgroup.option("--iss", "--issuer",
                     envvar=["OIDC_ISS", "OIDC_ISSUER"], show_envvar=True,
                     help="url of issuer, configured account in oidc-agent for this issuer will be used")
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


@click.group()
@common_options
def cli(**kwargs):
    """
    ssh client wrapper for oidc-based authentication
    """
    pass


@cli.command(name="ssh", short_help="open a login shell or execute a command via ssh")
@common_options
@click.option("--dry-run", is_flag=True, help="print sshpass command and exit")
@optgroup("ssh options", help="supported options to be passed to SSH")
@optgroup.option("-p", metavar="<int>", type=int, default=SSH_PORT,
                 help="port to connect to on remote host")
@click.argument("hostname")
@click.argument("command", required=False, default=None)
def ssh(mc_endpoint, verify, token, oa_account, iss,
        dry_run, p, hostname, command):
    try:
        mc_url = init_endpoint(mc_endpoint, hostname, verify)
        at = init_token(token, oa_account, iss, mc_url, verify)
        username = init_user(mc_url, at, verify)
        if dry_run:
            password = str_init_token(token, oa_account, iss)
            ssh_opts = ""
            if p and p != SSH_PORT:
                ssh_opts += f" -p {p}"
            sshpass_cmd = f"sshpass -P 'Access Token' -p {password} ssh {ssh_opts} {username}@{hostname}"
            if command:
                sshpass_cmd = f"{sshpass_cmd} '{command}'"
            print(sshpass_cmd)
        else:
            if command is None:
                ssh_interactive(hostname, username, at, p)
            else:
                ssh_exec(hostname, username, at, p, command)
    except Exception as e:
        print(e)


@cli.command(name="scp", short_help="secure file copy")
@common_options
@click.option("--dry-run", is_flag=True, help="print sshpass command and exit")
@optgroup("scp options", help="supported options to be passed to SCP")
@optgroup.option("-P", "port", metavar="<int>", type=int, default=SSH_PORT,
                 help="port to connect to on remote host")
@optgroup.option("-r", "recursive", is_flag=True,
                 help="recursively copy entire directories")
@optgroup.option("-p", "preserve_times", is_flag=True,
                 help="preserve modification times and access times from the original file")
@click.argument("source", nargs=-1, required=True, callback=validate_scp_source)
@click.argument("target", callback=validate_scp_target)
def scp(mc_endpoint, verify, token, oa_account, iss,
        dry_run, port, recursive, preserve_times,
        source, target):
    if dry_run:
        password = str_init_token(token, oa_account, iss)
        scp_opts = ""
        if recursive:
            scp_opts += " -r"
        if preserve_times:
            scp_opts += " -p"
        if port and port != SSH_PORT:
            scp_opts += f" -P {port}"
        sshpass_cmd = f"sshpass -P 'Access Token' -p {password} scp {scp_opts}"
    try:
        dest_path = target.get("path", ".")
        dest_host = target.get("host", None)
        dest_is_remote = dest_host is not None
        if dest_is_remote:
            dest_endpoint = init_endpoint(mc_endpoint, dest_host, verify)
            at = init_token(token, oa_account, iss, dest_endpoint, verify)
            username = init_user(dest_endpoint, at, verify)
        for src in source:
            src_path = src.get("path", ".")
            src_host = src.get("host", None)
            src_is_remote = src_host is not None
            if src_is_remote:
                src_endpoint = init_endpoint(mc_endpoint, src_host, verify)
                at = init_token(token, oa_account, iss, src_endpoint, verify)
                username = init_user(src_endpoint, at, verify)

            if not src_is_remote and not dest_is_remote:
                raise Exception(
                    "No remote host specified. Use regular cp instead.")
            elif src_is_remote and dest_is_remote:
                raise Exception("scp between remote hosts not yet supported.")
            elif src_is_remote:
                if dry_run:
                    sshpass_cmd += f" {username}@{src_host}:{src_path}"
                else:
                    scp_get(src_host, username, at, port,
                            src_path, dest_path,
                            recursive=recursive, preserve_times=preserve_times)
            else:
                if dry_run:
                    sshpass_cmd += f" {src_path}"
                else:
                    scp_put(dest_host, username, at, port,
                            src_path, dest_path,
                            recursive=recursive, preserve_times=preserve_times)
        if dry_run:
            if dest_is_remote:
                sshpass_cmd += f" {username}@{dest_host}:{dest_path}"
            else:
                sshpass_cmd += f" {dest_path}"
            print(sshpass_cmd)
    except PermissionError as e:
        print(f"{e.filename.decode('utf-8')}: Permission denied")
    except IsADirectoryError as e:
        print((f"{e.filename}: not a regular file"))
    except FileNotFoundError as e:
        print(f"{e.filename}: No such file or directory")
    except Exception as e:
        print(e)


@cli.command(name="sftp", short_help="--- Not implemented ---")
def sftp():
    print("Not implemented.")


if __name__ == '__main__':
    cli()
