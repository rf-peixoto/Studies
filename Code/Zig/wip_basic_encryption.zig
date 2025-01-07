const std = @import("std");
const fs = std.fs;
const crypto = std.crypto;
const mem = std.mem;

pub fn main() !void {
    const allocator = std.heap.page_allocator;

    // Use a basic built-in argument parser for demonstration.
    var args_it = std.process.args.iterator();
    _ = try args_it.next(); // Skip the executable name.

    const operation = try args_it.nextOptional() orelse return usage();
    if (!mem.eql(u8, operation, "encrypt") and !mem.eql(u8, operation, "decrypt")) {
        return usage();
    }

    const target_path = try args_it.nextOptional() orelse return usage();

    // Optional arguments with default values
    var algorithm: []const u8 = "aes-256-gcm";
    var password: []const u8 = "default_password";
    var iterations: u32 = 100_000;
    var salt_size: usize = 16; // Default salt size, in bytes.

    while (true) {
        const opt_arg = try args_it.nextOptional();
        if (opt_arg == null) break;
        const token = opt_arg.?;
        if (mem.startsWith(u8, token, "--password=")) {
            password = token[11..];
        } else if (mem.startsWith(u8, token, "--iterations=")) {
            iterations = std.fmt.parseUnsignedInt(u32, token[13..]) catch return usage();
        } else if (mem.startsWith(u8, token, "--salt-size=")) {
            salt_size = std.fmt.parseUnsignedInt(usize, token[12..]) catch return usage();
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
        \\Example:
        \\  encrypt_decrypt encrypt ./somefile --password=secret --iterations=200000 --salt-size=32
        \\  encrypt_decrypt decrypt ./somefile.enc --password=secret
        \\
    , .{});
    return error.Usage;
}

// Recursively process a directory
fn processDirectory(
    operation: []const u8,
    dir_path: []const u8,
    password: []const u8,
    iterations: u32,
    salt_size: usize,
) !void {
    var stack_allocator = std.heap.FixedBufferAllocator.init(std.mem.zeroes([1024]u8));
    const alloc = stack_allocator.allocator();

    const it = try fs.cwd().openIterableDir(dir_path, .{});
    defer it.close();

    while (true) {
        const next_entry = try it.nextEntry();
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

// Encrypt or decrypt a file
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
        const output_path = try std.fs.path.joinExt(std.heap.page_allocator, file_path, enc_suffix);
        defer std.heap.page_allocator.free(output_path);

        try encryptFile(file_path, output_path, password, iterations, salt_size);
    } else {
        // For decryption, create a ".dec" file as output.
        const output_path = try std.fs.path.joinExt(std.heap.page_allocator, file_path, dec_suffix);
        defer std.heap.page_allocator.free(output_path);

        try decryptFile(file_path, output_path, password, iterations, salt_size);
    }
}

// Encrypt a file using AES-256-GCM
fn encryptFile(
    input_path: []const u8,
    output_path: []const u8,
    password: []const u8,
    iterations: u32,
    salt_size: usize,
) !void {
    const allocator = std.heap.page_allocator;

    // Read entire file. For large files, implement streaming instead.
    const input_data = try fs.cwd().readFileAlloc(allocator, input_path, 65536);
    defer allocator.free(input_data);

    // Generate random salt.
    const salt = try std.crypto.random.bytesAlloc(allocator, salt_size);
    defer allocator.free(salt);

    // Derive key using PBKDF2 with HMAC-SHA256.
    const derived_key_size = 32; // 256-bit key
    var derived_key: [derived_key_size]u8 = undefined;
    try deriveKeyFromPassword(password, salt, iterations, &derived_key);

    // Generate random nonce for AES-GCM (12 bytes recommended).
    const nonce = try std.crypto.random.bytesAlloc(allocator, 12);
    defer allocator.free(nonce);

    // Create an output buffer. Format:
    // [salt (salt_size bytes) | nonce (12 bytes) | ciphertext (...) | tag (16 bytes)]
    var output_buffer = std.heap.page_allocator.createSlice(u8, 0);
    defer allocator.free(output_buffer);

    try output_buffer.appendSlice(salt);
    try output_buffer.appendSlice(nonce);

    // Perform AES-GCM encryption.
    const cipher = crypto.cipher.aes.Cipher.init(crypto.cipher.aes.KeySize.bits256, &derived_key);
    var gcm = crypto.modes.gcm.Gcm.init(&cipher, nonce);
    try gcm.encrypt(input_data, &output_buffer);
    const tag_bytes = gcm.finalTag();
    try output_buffer.appendSlice(tag_bytes);

    // Write the encrypted data to the output file.
    const out_file = try fs.cwd().createFile(output_path, .{});
    defer out_file.close();
    try out_file.writeAll(output_buffer);
}

// Decrypt a file using AES-256-GCM
fn decryptFile(
    input_path: []const u8,
    output_path: []const u8,
    password: []const u8,
    iterations: u32,
    salt_size: usize,
) !void {
    const allocator = std.heap.page_allocator;

    // Read entire file
    const in_data = try fs.cwd().readFileAlloc(allocator, input_path, 65536);
    defer allocator.free(in_data);

    // For a valid AES-GCM file with salt, nonce, and tag:
    // - salt_size: known or passed as an argument (used here).
    // - nonce: 12 bytes
    // - tag: 16 bytes
    // The rest is ciphertext.
    if (in_data.len < salt_size + 12 + 16) {
        std.log.err("Input file is too small to contain required cryptographic data.\n", .{});
        return;
    }

    const salt = in_data[0 .. salt_size];
    const nonce = in_data[salt_size .. salt_size + 12];
    const ciphertext = in_data[salt_size + 12 .. in_data.len - 16];
    const tag = in_data[in_data.len - 16 ..];

    // Derive the key from the provided password
    const derived_key_size = 32;
    var derived_key: [derived_key_size]u8 = undefined;
    try deriveKeyFromPassword(password, salt, iterations, &derived_key);

    // Decrypt
    const cipher = crypto.cipher.aes.Cipher.init(crypto.cipher.aes.KeySize.bits256, &derived_key);
    var gcm = crypto.modes.gcm.Gcm.init(&cipher, nonce);

    var output_buffer = std.heap.page_allocator.createSlice(u8, 0);
    defer std.heap.page_allocator.free(output_buffer);

    try gcm.decrypt(ciphertext, &output_buffer);
    const computed_tag = gcm.finalTag();
    if (!mem.eql(u8, computed_tag, tag)) {
        std.log.err("Decryption failed: authentication tag mismatch.\n", .{});
        return;
    }

    // Write the decrypted data to output file
    const out_file = try fs.cwd().createFile(output_path, .{});
    defer out_file.close();
    try out_file.writeAll(output_buffer);
}

// PBKDF2-HMAC-SHA256 key derivation
fn deriveKeyFromPassword(
    password: []const u8,
    salt: []const u8,
    iterations: u32,
    out_key: *[32]u8,
) !void {
    const KeySize = 32;
    // PBKDF2 with HmacSHA256
    const prf = crypto.pbkdf2.HmacSHA256{
        .secret_key = password,
    };
    try crypto.pbkdf2.pbkdf2(
        &prf,
        salt,
        iterations,
        out_key[0..KeySize],
    );
}
