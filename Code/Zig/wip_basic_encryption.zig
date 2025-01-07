const std = @import("std");
const fs = std.fs;
const crypto = std.crypto;
const mem = std.mem;

pub fn main() !void {
    const allocator = std.heap.page_allocator;

    const args_slice = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, args_slice);

    if (args_slice.len < 3) {
        return usage();
    }

    const operation = args_slice[1];
    if (!mem.eql(u8, operation, "encrypt") and !mem.eql(u8, operation, "decrypt")) {
        return usage();
    }

    const target_path = args_slice[2];

    var algorithm: []const u8 = "aes-256-gcm";
    var password: []const u8 = "default_password";
    var iterations: u32 = 100000;
    var salt_size: usize = 16;

    var i: usize = 3;
    while (i < args_slice.len) {
        const token = args_slice[i];
        i += 1;

        if (mem.startsWith(u8, token, "--password=")) {
            password = token[11..];
        } else if (mem.startsWith(u8, token, "--iterations=")) {
            iterations = try std.fmt.parseInt(u32, token[13..], 10);
        } else if (mem.startsWith(u8, token, "--salt-size=")) {
            salt_size = try std.fmt.parseInt(usize, token[12..], 10);
        } else if (mem.startsWith(u8, token, "--algorithm=")) {
            algorithm = token[12..];
        } else {
            return usage();
        }
    }

    if (!mem.eql(u8, algorithm, "aes-256-gcm")) {
        std.log.err("Unsupported or unimplemented algorithm: {s}\n", .{algorithm});
        return;
    }

    const stat_info = try fs.cwd().statAlloc(allocator, target_path);
    defer allocator.free(stat_info);

    if (stat_info.kind == .Directory) {
        try processDirectory(operation, target_path, password, iterations, salt_size);
    } else {
        try processFile(operation, target_path, password, iterations, salt_size);
    }
}

fn usage() !void {
    std.log.err(
        \\Usage:
        \\  encrypt_decrypt <encrypt|decrypt> <target_path> [options...]
        \\
        \\Options:
        \\  --password=<password>      (default: "default_password")
        \\  --iterations=<number>      (default: 100000)
        \\  --salt-size=<number>       (default: 16 bytes)
        \\  --algorithm=aes-256-gcm    (default: "aes-256-gcm")
        \\
        \\Example:
        \\  encrypt_decrypt encrypt ./somefile --password=secret --iterations=200000 --salt-size=32
        \\  encrypt_decrypt decrypt ./somefile.enc --password=secret
        \\
    , .{});
    return error.Usage;
}

fn processDirectory(
    operation: []const u8,
    dir_path: []const u8,
    password: []const u8,
    iterations: u32,
    salt_size: usize,
) !void {
    var stack_allocator = std.heap.FixedBufferAllocator.init(std.mem.zeroes([1024]u8));
    const alloc = stack_allocator.allocator();

    const dir_iter = try fs.cwd().openIterableDir(dir_path, .{});
    defer dir_iter.close();

    while (true) {
        const next_entry = try dir_iter.nextEntry();
        if (next_entry == null) break;
        const entry = next_entry.?;

        if (mem.eql(u8, entry.name, ".")) continue;
        if (mem.eql(u8, entry.name, "..")) continue;

        const path_buffer = try fs.path.joinAlloc(alloc, dir_path, entry.name);
        defer alloc.free(path_buffer);

        const stat_info = try fs.cwd().statAlloc(alloc, path_buffer);
        defer alloc.free(stat_info);

        if (stat_info.kind == .Directory) {
            try processDirectory(operation, path_buffer, password, iterations, salt_size);
        } else {
            try processFile(operation, path_buffer, password, iterations, salt_size);
        }
    }
}

fn processFile(
    operation: []const u8,
    file_path: []const u8,
    password: []const u8,
    iterations: u32,
    salt_size: usize,
) !void {
    const enc_suffix = ".enc";
    const dec_suffix = ".dec";

    if (mem.eql(u8, operation, "encrypt")) {
        const output_path = try fs.path.joinExt(std.heap.page_allocator, file_path, enc_suffix);
        defer std.heap.page_allocator.free(output_path);

        try encryptFile(file_path, output_path, password, iterations, salt_size);
    } else {
        const output_path = try fs.path.joinExt(std.heap.page_allocator, file_path, dec_suffix);
        defer std.heap.page_allocator.free(output_path);

        try decryptFile(file_path, output_path, password, iterations, salt_size);
    }
}

fn encryptFile(
    input_path: []const u8,
    output_path: []const u8,
    password: []const u8,
    iterations: u32,
    salt_size: usize,
) !void {
    const allocator = std.heap.page_allocator;

    const input_data = try fs.cwd().readFileAlloc(allocator, input_path, 65536);
    defer allocator.free(input_data);

    const salt = try crypto.random.bytesAlloc(allocator, salt_size);
    defer allocator.free(salt);

    const derived_key_size = 32;
    var derived_key: [derived_key_size]u8 = undefined;
    try deriveKeyFromPassword(password, salt, iterations, &derived_key);

    const nonce = try crypto.random.bytesAlloc(allocator, 12);
    defer allocator.free(nonce);

    var output_buffer = allocator.createSlice(u8, 0);
    defer allocator.free(output_buffer);

    try output_buffer.appendSlice(salt);
    try output_buffer.appendSlice(nonce);

    const cipher = crypto.cipher.aes.Cipher.init(crypto.cipher.aes.KeySize.bits256, &derived_key);
    var gcm = crypto.modes.gcm.Gcm.init(&cipher, nonce);
    try gcm.encrypt(input_data, &output_buffer);
    const tag_bytes = gcm.finalTag();
    try output_buffer.appendSlice(tag_bytes);

    const out_file = try fs.cwd().createFile(output_path, .{});
    defer out_file.close();
    try out_file.writeAll(output_buffer);
}

fn decryptFile(
    input_path: []const u8,
    output_path: []const u8,
    password: []const u8,
    iterations: u32,
    salt_size: usize,
) !void {
    const allocator = std.heap.page_allocator;

    const in_data = try fs.cwd().readFileAlloc(allocator, input_path, 65536);
    defer allocator.free(in_data);

    if (in_data.len < salt_size + 12 + 16) {
        std.log.err("Input file is too small to contain required cryptographic data.\n", .{});
        return;
    }

    const salt = in_data[0 .. salt_size];
    const nonce = in_data[salt_size .. salt_size + 12];
    const ciphertext = in_data[salt_size + 12 .. in_data.len - 16];
    const tag = in_data[in_data.len - 16 ..];

    const derived_key_size = 32;
    var derived_key: [derived_key_size]u8 = undefined;
    try deriveKeyFromPassword(password, salt, iterations, &derived_key);

    const cipher = crypto.cipher.aes.Cipher.init(crypto.cipher.aes.KeySize.bits256, &derived_key);
    var gcm = crypto.modes.gcm.Gcm.init(&cipher, nonce);

    var output_buffer = allocator.createSlice(u8, 0);
    defer allocator.free(output_buffer);

    try gcm.decrypt(ciphertext, &output_buffer);
    const computed_tag = gcm.finalTag();
    if (!mem.eql(u8, computed_tag, tag)) {
        std.log.err("Decryption failed: authentication tag mismatch.\n", .{});
        return;
    }

    const out_file = try fs.cwd().createFile(output_path, .{});
    defer out_file.close();
    try out_file.writeAll(output_buffer);
}

fn deriveKeyFromPassword(
    password: []const u8,
    salt: []const u8,
    iterations: u32,
    out_key: *[32]u8,
) !void {
    const KeySize = 32;
    const prf = crypto.pbkdf2.HmacSHA256{ .secret_key = password };

    try crypto.pbkdf2.pbkdf2(
        &prf,
        salt,
        iterations,
        out_key[0..KeySize],
    );
}
