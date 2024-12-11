#!/usr/bin/env -S PYTHONPATH=../../../tools/extract-utils python3

import os
import sys
import subprocess
import shutil
import tempfile

def error_handler(extract_out):
    if os.path.exists(extract_out):
        print(f"Error detected, cleaning temporal working directory {extract_out}")
        shutil.rmtree(extract_out)

def usage():
    print("Usage: ./extract_files.py <rom-zip>")
    sys.exit(1)

def get_path(extract_out, filename):
    return os.path.join(extract_out, filename)

def run_command(command):
    try:
        subprocess.run(command, check=True, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        sys.exit(1)

def clean_and_create_directories(directories):
    for directory in directories:
        if os.path.exists(directory):
            shutil.rmtree(directory)
        os.makedirs(directory, exist_ok=True)

def main():
    EXTRACT_OTA = "../../../prebuilts/extract-tools/linux-x86/bin/ota_extractor"
    UNPACKBOOTIMG = "../../../system/tools/mkbootimg/unpack_bootimg.py"

    if len(sys.argv) != 2:
        usage()

    ROM_ZIP = sys.argv[1]

    for required_file in [UNPACKBOOTIMG, EXTRACT_OTA, ROM_ZIP]:
        if not os.path.isfile(required_file):
            print(f"Missing {required_file}, please check the path.")
            sys.exit(1)

    directories = [
        "./modules/vendor_dlkm", "./modules/system_dlkm", "./modules/vendor_boot",
        "./images", "./images/dtbs"
    ]
    clean_and_create_directories(directories)

    extract_out = tempfile.mkdtemp()
    print(f"Using {extract_out} as working directory")

    try:
        print(f"Extracting the payload from {ROM_ZIP}")
        run_command(f"unzip {ROM_ZIP} payload.bin -d {extract_out}")

        print("Extracting OTA images")
        run_command(f"{EXTRACT_OTA} -payload {get_path(extract_out, 'payload.bin')} -output_dir {extract_out} -partitions boot,dtbo,vendor_boot,vendor_dlkm,system_dlkm")

        print("Extracting the kernel image from boot.img")
        boot_out = os.path.join(extract_out, "boot-out")
        os.makedirs(boot_out, exist_ok=True)
        run_command(f"python3 {UNPACKBOOTIMG} --boot_img {get_path(extract_out, 'boot.img')} --out {boot_out} --format mkbootimg")
        shutil.copy(os.path.join(boot_out, "kernel"), "./images/kernel")

        print("Extracting the ramdisk kernel modules and DTB")
        vendor_boot_out = os.path.join(extract_out, "vendor_boot-out")
        os.makedirs(vendor_boot_out, exist_ok=True)
        run_command(f"python3 {UNPACKBOOTIMG} --boot_img {get_path(extract_out, 'vendor_boot.img')} --out {vendor_boot_out} --format mkbootimg")
        ramdisk_out = os.path.join(vendor_boot_out, "ramdisk")
        os.makedirs(ramdisk_out, exist_ok=True)
        run_command(f"unlz4 {os.path.join(vendor_boot_out, 'vendor_ramdisk00')} {os.path.join(vendor_boot_out, 'vendor_ramdisk')}")
        run_command(f"cpio -i -F {os.path.join(vendor_boot_out, 'vendor_ramdisk')} -D {ramdisk_out}")

        for root, _, files in os.walk(ramdisk_out):
            for file in files:
                if file.endswith(".ko") or file.startswith("modules."):
                    shutil.copy(os.path.join(root, file), "./modules/vendor_boot/")

        print("Extracting the dlkm kernel modules")
        for partition, target in [("vendor_dlkm", "./modules/vendor_dlkm"), ("system_dlkm", "./modules/system_dlkm")]:
            partition_out = os.path.join(extract_out, partition)
            os.makedirs(partition_out, exist_ok=True)
            run_command(f"fsck.erofs --extract={partition_out} {get_path(extract_out, f'{partition}.img')}")
            for root, _, files in os.walk(partition_out):
                for file in files:
                    if file.endswith(".ko") or file.startswith("modules."):
                        shutil.copy(os.path.join(root, file), target)

        print("Extracting DTBO and DTBs")
        extract_dtb_script = os.path.join(extract_out, "extract_dtb.py")
        run_command(f"curl -sSL \"https://raw.githubusercontent.com/PabloCastellano/extract-dtb/master/extract_dtb/extract_dtb.py\" -o {extract_dtb_script}")
        run_command(f"python3 {extract_dtb_script} {os.path.join(vendor_boot_out, 'dtb')} -o {os.path.join(extract_out, 'dtbs')}")

        for root, _, files in os.walk(os.path.join(extract_out, "dtbs")):
            for file in files:
                if file.endswith(".dtb"):
                    shutil.copy(os.path.join(root, file), "./images/dtbs/")

        shutil.copy(get_path(extract_out, "dtbo.img"), "./images/dtbo.img")
        print("Done")

    except Exception as e:
        error_handler(extract_out)
        print(f"An error occurred: {e}")
        sys.exit(1)

    finally:
        shutil.rmtree(extract_out)
        print("Extracted files successfully")

if __name__ == "__main__":
    main()
