#!/usr/bin/env python3
"""Because ClickOnce is a plague upon the world"""

import pathlib
from pathlib import Path, PurePath, PureWindowsPath, PurePosixPath
import sys
import typing
from uri import URI
import urllib.request, urllib.parse
import xml.etree.ElementTree as ETree

def join_uri(self: URI, *items) -> URI:
    return self.resolve(uri=None, path=self.path.joinpath(*items))

ns = {"asmv1": "urn:schemas-microsoft-com:asm.v1", "asmv2": "urn:schemas-microsoft-com:asm.v2"}

def download_file(url: typing.Union[str, urllib.request.Request, URI], output: Path):
    if isinstance(url, URI):
        url = str(url)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open(mode="wb", encoding=None) as outfile:
        with urllib.request.urlopen(url) as infile:
            outfile.write(infile.read())


def download_file_if_not_present_size(
    url: typing.Union[str, urllib.request.Request, URI],
    output: Path,
    size: int,
):
    if output.exists() and output.stat().st_size == size:
        print("   -- File already present, skipping")
        return
    download_file(url, output)

# -------------

class DependentAssembly:
    def __init__(
        self,
        codebase: str,
        size: int,
        direct: bool,
    ):
        self.codebase = codebase
        self.size = size
        self.direct = direct

    def _get_path_components(self):
        return [
            urllib.parse.quote(part) for part in PurePosixPath(
                self.codebase if self.direct else self.codebase + ".deploy"
            ).parts]

    def get_remote_relative_path(self) -> PurePosixPath:
        return PurePosixPath(*self._get_path_components())

    def get_remote_base_path(self, deployment_codebase: URI) -> URI:
        return join_uri(deployment_codebase, PurePosixPath(*self._get_path_components()[:-1]))

    def get_remote_path(self, deployment_codebase: URI) -> URI:
        subpath = PurePosixPath(*self._get_path_components())
        resolved = join_uri(deployment_codebase, subpath)
        # print("Resolved remote {} from posixpath {} and original url {}".format(resolved, subpath, deployment_codebase))
        return resolved

    def get_local_path(self, destination: PurePath) -> PurePath:
        return destination / self.codebase

    @staticmethod
    def Read(da: ETree.Element, direct: bool = False) -> 'DependentAssembly':
        return DependentAssembly(
            str(PureWindowsPath(da.attrib["codebase"]).as_posix()),
            int(da.attrib["size"]),
            direct=direct)


def download_manifest(manifest: Path, remote_codebase: URI, destination: Path):
    tree = ETree.parse(str(manifest))
    root = tree.getroot()
    destination.mkdir(parents=True, exist_ok=True)
    print("Downloading manifest {}".format(manifest))
    print("Pulling from remote {}\nWriting to local {}".format(remote_codebase, destination))

    for d in root.findall("./asmv2:dependency/asmv2:dependentAssembly[@dependencyType='install']", ns):
        da = DependentAssembly.Read(d, direct=False)
        codebase_remote = da.get_remote_path(remote_codebase)
        codebase_local = da.get_local_path(destination)
        print("Found installation {}\nDownloading to {}\n ... from {}".format(d, codebase_local, str(codebase_remote)))
        download_file_if_not_present_size(str(codebase_remote), Path(codebase_local), da.size)

    for f in root.findall("./asmv2:file", ns):
        name = PurePosixPath(PureWindowsPath(f.attrib["name"]).as_posix())
        remote_name = PurePosixPath(str(name) + ".deploy")
        local_name = name
        remote = join_uri(remote_codebase, remote_name)
        local = destination.joinpath(local_name)
        print("Found file {}\nDownloading to {}\n ... from {}".format(name, local, str(remote)))
        download_file_if_not_present_size(str(remote), Path(local), int(f.attrib["size"]))


def download_application(app_manifest: Path, destination: Path):
    tree = ETree.parse(str(app_manifest))
    root = tree.getroot()
    deployment_codebase = URI(
        root.find("asmv2:deployment/asmv2:deploymentProvider", ns).attrib["codebase"]).resolve(".")
    print("Using codebase {}".format(deployment_codebase))
    for d in root.findall("./asmv2:dependency/asmv2:dependentAssembly[@dependencyType='install']", ns):
        da = DependentAssembly.Read(d, direct=True)
        codebase_remote = da.get_remote_path(deployment_codebase)
        codebase_local = da.get_local_path(destination)
        print("Found installation {}\nDownloading to {}\n ... from {}".format(d, codebase_local, str(codebase_remote)))
        download_file_if_not_present_size(codebase_remote, Path(codebase_local), da.size)
        download_manifest(
            Path(codebase_local),
            da.get_remote_base_path(deployment_codebase),
            Path(da.get_local_path(destination).parent))


def main(argv):
    app_manifest = Path(argv[1])
    download_path = Path("./unpack")
    download_path.mkdir(exist_ok=True)
    download_application(app_manifest, download_path)


if __name__ == '__main__':
    main(sys.argv)
