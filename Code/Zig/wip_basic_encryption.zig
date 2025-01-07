const std = @import("std");
const fs = std.fs;
const crypto = std.crypto;
const mem = std.mem;

pub fn main() !void {
    const allocator = std.heap.page_allocator;

    // Obtain all command-line arguments as a slice
    const args_slice = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, args_slice);

    // We expect at least 3 arguments:
    //   1) program name (index 0)
    //   2) operation: "encrypt" or "decrypt" (index 1)
    //   3) path to file or folder (index 2)
    if (args_slice.len < 3) {
        return usage();
    }

    // Operation: "encrypt" or "decrypt"
    const operation = args_slice[1];
    if (!mem.eql(u8, operation, "encrypt") and !mem.eql(u8, operation, "decrypt")) {
        return usage();
    }

    // Target path
    const target_path = args_slice[2];

    // Defaults for optional arguments
    var algorithm: []const u8 = "aes-256-gcm";
    var password: []const u8 = "default_password";
    var iterations: u32 = 100_000;
    var salt_size: usize = 16; // default salt size in bytes

    // Process remaining arguments (index 3 and beyond)
    var i: usize = 3;
    while (i < args_slice.len) {
        const token = args_slice[i];
        i += 1;

        if (mem.startsWith(u8, token, "--password=")) {
            password = token[11..];
        } else if (mem.startsWith(u8, token, "--iterations=")) {
            // Parse an unsigned integer from a substring (base 10)
            iterations = try std.fmt.parseInt(u32, token[13..], 10);
        } else if (mem.startsWith(u8, token, "--salt-size=")) {
            // Parse an unsigned integer from a substring (base 10)
            salt_size = try std.fmt.parseInt(usize, token[12..], 10);
        } else if (mem.startsWith(u8, token, "--algorithm=")) {
            algorithm = token[12..];
        } else {
            return usage();
        }
    }

    // Check algorithm (only AES-256-GCM is implemented in this example)
    if (!mem.eql(u8, algorithm, "aes-256-gcm")) {
        std.log.err("Unsupported or unimplemented algorithm: {s}\n", .{algorithm});
        return;
    }

    // Check if target is a file or folder
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

/// Recursively process a directory
fn processDirectory(
    operation: []const u8,
    dir_path: []const u8,
    password: []const u8,
    iterations: u32,
    salt_size: usize,
) !void {
    // For demonstration, use a small fixed buffer to join path strings
    var stack_allocator = std.heap.FixedBufferAllocator.init(std.mem.zeroes([1024]u8));
    const alloc = stack_allocator.allocator();

    const dir_iter = try fs.cwd().openIterableDir(dir_path, .{});
    defer dir_iter.close();

    while (true) {
        const next_entry = try dir_iter.nextEntry();
        if (next_entry == null) break;
        const entry = next_entry.?;

        // Skip "." and ".." entries
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

/// Encrypt or decrypt a file
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
        // Append .enc
        const output_path = try fs.path.joinExt(std.heap.page_allocator, file_path, enc_suffix);
        defer std.heap.page_allocator.free(output_path);

        try encryptFile(file_path, output_path, password, iterations, salt_size);
    } else {
        // Append .dec
        const output_path = try fs.path.joinExt(std.heap.page_allocator, file_path, dec_suffix);
        defer std.heap.page_allocator.free(output_path);

        try decryptFile(file_path, output_path, password, iterations, salt_size);
    }
}

/// Encrypt a file using AES-256-GCM
fn encryptFile(
    input_path: []const u8,
    output_path: []const u8,
    password: []const u8,
    iterations: u32,
    salt_size: usize,
) !void {
    const allocator = std.heap.page_allocator;

    // Read the entire file (for large files, a streaming approach is recommended)
    const input_data = try fs.cwd().readFileAlloc(allocator, input_path, 65536);
    defer allocator.free(input_data);

    // Generate random salt
    const salt = try crypto.random.bytesAlloc(allocator, salt_size);
    defer allocator.free(salt);

    // Derive key using PBKDF2 with HMAC-SHA256
    const derived_key_size = 32; // 256-bit
    var derived_key: [derived_key_size]u8 = undefined;
    try deriveKeyFromPassword(password, salt, iterations, &derived_key);

    // Generate random nonce for AES-GCM (12 bytes recommended)
    const nonce = try crypto.random.bytesAlloc(allocator, 12);
    defer allocator.free(nonce);

    // Format of the output file:
    //   [salt (salt_size bytes) | nonce (12 bytes) | ciphertext... | tag (16 bytes)]
    var output_buffer = allocator.createSlice(u8, 0);
    defer allocator.free(output_buffer);

    try output_buffer.appendSlice(salt);
    try output_buffer.appendSlice(nonce);

    const cipher = crypto.cipher.aes.Cipher.init(crypto.cipher.aes.KeySize.bits256, &derived_key);
    var gcm = crypto.modes.gcm.Gcm.init(&cipher, nonce);
    try gcm.encrypt(input_data, &output_buffer);
    const tag_bytes = gcm.finalTag();

    try output_buffer.appendSlice(tag_bytes);

    // Write to output file
    const out_file = try fs.cwd().createFile(output_path, .{});
    defer out_file.close();
    try out_file.writeAll(output_buffer);
}

/// Decrypt a file using AES-256-GCM
fn decryptFile(
    input_path: []const u8,
    output_path: []const u8,
    password: []const u8,
    iterations: u32,
    salt_size: usize,
) !void {
    const allocator = std.heap.page_allocator;

    // Read the entire file
    const in_data = try fs.cwd().readFileAlloc(allocator, input_path, 65536);
    defer allocator.free(in_data);

    // Verify file has enough data: salt + nonce + tag at minimum
    if (in_data.len < salt_size + 12 + 16) {
        std.log.err("Input file is too small to contain required cryptographic data.\n", .{});
        return;
    }

    const salt = in_data[0 .. salt_size];
    const nonce = in_data[salt_size .. salt_size + 12];
    const ciphertext = in_data[salt_size + 12 .. in_data.len - 16];
    const tag = in_data[in_data.len - 16 ..];

    // Derive the key
    const derived_key_size = 32;
    var derived_key: [derived_key_size]u8 = undefined;
    try deriveKeyFromPassword(password, salt, iterations, &derived_key);

    const cipher = crypto.cipher.aes.Cipher.init(crypto.cipher.aes.KeySize.bits256, &derived_key);
    var gcm = crypto.modes.gcm.Gcm.init(&cipher, nonce);

    var output_buffer = allocator.createSlice(u8, 0);
    defer allocator.free(output_buffer);

    try gcm.decrypt(ciphertext, &output_buffer);

    // Validate authentication tag
    const computed_tag = gcm.finalTag();
    if (!mem.eql(u8, computed_tag, tag)) {
        std.log.err("Decryption failed: authentication tag mismatch.\n", .{});
        return;
    }

    // Write the decrypted data
    const out_file = try fs.cwd().createFile(output_path, .{});
    defer out_file.close();
    try out_file.writeAll(output_buffer);
}

/// PBKDF2-HMAC-SHA256 key derivation
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
