use std::io::{self, Read, Write};

use brotli::{
    BrotliDecompressStream, BrotliResult, BrotliState, CompressorReader, HeapAlloc, HuffmanCode,
};
use flate2::write::{DeflateEncoder, GzEncoder, MultiGzDecoder, ZlibEncoder};
use flate2::{Compression, Decompress, FlushDecompress, Status};
use zstd::stream::raw::{DParameter, Decoder, Operation};

const BLOCK: usize = 8192;

/// 只统计字节数量的出口，不保存完整解码正文。
#[derive(Default)]
struct Counter {
    bytes: usize,
    max_write: usize,
}

impl Write for Counter {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        self.bytes += bytes.len();
        self.max_write = self.max_write.max(bytes.len());
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

/// 记录格式结论、输出数量及是否在传输末尾前产生明文。
#[derive(Debug)]
struct Observation {
    state: &'static str,
    bytes: usize,
    early: bool,
    max_write: usize,
}

fn gzip(input: &[u8], size: usize) -> Observation {
    let mut decoder = MultiGzDecoder::new(Counter::default());
    let mut state = "ok";
    let mut early = false;
    let mut supplied = 0;
    for part in input.chunks(size) {
        supplied += part.len();
        if decoder
            .write_all(part)
            .and_then(|()| decoder.flush())
            .is_err()
        {
            state = "error";
            break;
        }
        early |= supplied < input.len() && decoder.get_ref().bytes > 0;
    }
    if state == "ok" && decoder.try_finish().is_err() {
        state = "error";
    }
    Observation {
        state,
        bytes: decoder.get_ref().bytes,
        early,
        max_write: decoder.get_ref().max_write,
    }
}

fn deflate(input: &[u8], size: usize, zlib: bool) -> Observation {
    let mut decoder = Decompress::new(zlib);
    let mut result = Observation {
        state: "truncated",
        bytes: 0,
        early: false,
        max_write: 0,
    };
    let mut ended = false;
    let mut supplied = 0;
    for part in input.chunks(size).chain(std::iter::once(&[][..])) {
        supplied += part.len();
        if ended {
            if !part.is_empty() {
                result.state = "trailing";
            }
            continue;
        }
        let mut offset = 0;
        loop {
            let mut out = [0; BLOCK];
            let before_in = decoder.total_in();
            let before_out = decoder.total_out();
            let status = decoder.decompress(&part[offset..], &mut out, FlushDecompress::None);
            let used = (decoder.total_in() - before_in) as usize;
            let made = (decoder.total_out() - before_out) as usize;
            offset += used;
            result.bytes += made;
            result.max_write = result.max_write.max(made);
            result.early |= supplied < input.len() && result.bytes > 0;
            match status {
                Err(_) => {
                    result.state = "error";
                    return result;
                }
                Ok(Status::StreamEnd) => {
                    ended = true;
                    result.state = if offset == part.len() {
                        "ok"
                    } else {
                        "trailing"
                    };
                    break;
                }
                _ => {}
            }
            if used == 0 && made == 0 {
                break;
            }
            if offset == part.len() && made < BLOCK {
                break;
            }
        }
    }
    result
}

fn brotli(input: &[u8], size: usize) -> Observation {
    let mut decoder = BrotliState::new_strict(
        HeapAlloc::<u8>::default(),
        HeapAlloc::<u32>::default(),
        HeapAlloc::<HuffmanCode>::default(),
    );
    let mut result = Observation {
        state: "truncated",
        bytes: 0,
        early: false,
        max_write: 0,
    };
    let mut ended = false;
    let mut supplied = 0;
    let mut total_out = 0;
    for part in input.chunks(size).chain(std::iter::once(&[][..])) {
        supplied += part.len();
        if ended {
            if !part.is_empty() {
                result.state = "trailing";
            }
            continue;
        }
        let mut available_in = part.len();
        let mut input_offset = 0;
        loop {
            let mut out = [0; BLOCK];
            let mut available_out = out.len();
            let mut output_offset = 0;
            let status = BrotliDecompressStream(
                &mut available_in,
                &mut input_offset,
                part,
                &mut available_out,
                &mut output_offset,
                &mut out,
                &mut total_out,
                &mut decoder,
            );
            result.bytes += output_offset;
            result.max_write = result.max_write.max(output_offset);
            result.early |= supplied < input.len() && result.bytes > 0;
            match status {
                BrotliResult::ResultFailure => {
                    result.state = "error";
                    return result;
                }
                BrotliResult::ResultSuccess => {
                    ended = true;
                    result.state = if available_in == 0 { "ok" } else { "trailing" };
                    break;
                }
                BrotliResult::NeedsMoreInput => {
                    assert_eq!(available_in, 0);
                    break;
                }
                BrotliResult::NeedsMoreOutput => {}
            }
        }
    }
    result
}

fn zstd(input: &[u8], size: usize) -> Observation {
    let mut decoder = Decoder::new().unwrap();
    decoder.set_parameter(DParameter::WindowLogMax(24)).unwrap();
    let mut result = Observation {
        state: "truncated",
        bytes: 0,
        early: false,
        max_write: 0,
    };
    let mut at_boundary = false;
    let mut supplied = 0;
    for part in input.chunks(size) {
        supplied += part.len();
        let mut offset = 0;
        loop {
            let mut out = [0; BLOCK];
            let status = match decoder.run_on_buffers(&part[offset..], &mut out) {
                Ok(status) => status,
                Err(_) => {
                    result.state = "error";
                    return result;
                }
            };
            offset += status.bytes_read;
            result.bytes += status.bytes_written;
            result.max_write = result.max_write.max(status.bytes_written);
            result.early |= supplied < input.len() && result.bytes > 0;
            at_boundary = status.remaining == 0;
            if at_boundary {
                if offset == part.len() {
                    break;
                }
                continue;
            }
            if status.bytes_read == 0 && status.bytes_written == 0 {
                break;
            }
            if offset == part.len() && status.bytes_written < BLOCK {
                break;
            }
        }
    }
    // 已结束时不能再以空输入启动新 frame，否则会误把合法边界记成截断。
    if !at_boundary {
        loop {
            let mut out = [0; BLOCK];
            let status = match decoder.run_on_buffers(&[], &mut out) {
                Ok(status) => status,
                Err(_) => {
                    result.state = "error";
                    return result;
                }
            };
            result.bytes += status.bytes_written;
            result.max_write = result.max_write.max(status.bytes_written);
            at_boundary = status.remaining == 0;
            if at_boundary || status.bytes_written == 0 {
                break;
            }
        }
    }
    result.state = if at_boundary { "ok" } else { "truncated" };
    result
}

fn emit(name: &str, size: usize, result: Observation, expected: bool) {
    assert_eq!(result.state == "ok", expected, "{name}/{size}: {result:?}");
    println!(
        "{name}\t{size}\t{}\t{}\t{}\t{}",
        result.state, result.bytes, result.early, result.max_write
    );
}

fn main() {
    let payload = b": synthetic observation payload\n\n".repeat(65536);
    let mut gz = GzEncoder::new(Vec::new(), Compression::default());
    gz.write_all(&payload).unwrap();
    let gz = gz.finish().unwrap();
    let mut zl = ZlibEncoder::new(Vec::new(), Compression::default());
    zl.write_all(&payload).unwrap();
    let zl = zl.finish().unwrap();
    let mut raw = DeflateEncoder::new(Vec::new(), Compression::default());
    raw.write_all(&payload).unwrap();
    let raw = raw.finish().unwrap();
    let mut br = Vec::new();
    CompressorReader::new(payload.as_slice(), 4096, 4, 22)
        .read_to_end(&mut br)
        .unwrap();
    let zs = zstd::stream::encode_all(payload.as_slice(), 1).unwrap();
    println!("case\tchunk\tstate\toutput_bytes\tearly_output\tmax_output_slice");
    for size in [1, 7, 1024] {
        let cases = [
            ("gzip_long", gzip(&gz, size)),
            ("zlib_long", deflate(&zl, size, true)),
            ("raw_long", deflate(&raw, size, false)),
            ("br_long", brotli(&br, size)),
            ("zstd_long", zstd(&zs, size)),
        ];
        for (name, result) in cases {
            assert_eq!(result.bytes, payload.len());
            emit(name, size, result, true);
        }
    }
    let gz_multi = [gz.as_slice(), gz.as_slice()].concat();
    emit("gzip_members", 7, gzip(&gz_multi, 7), true);
    let mut bad_crc = gz.clone();
    let crc = bad_crc.len() - 8;
    bad_crc[crc] ^= 1;
    emit("gzip_crc", 7, gzip(&bad_crc, 7), false);
    emit(
        "gzip_second_crc",
        7,
        gzip(&[gz.as_slice(), bad_crc.as_slice()].concat(), 7),
        false,
    );
    emit("gzip_cut_footer", 7, gzip(&gz[..gz.len() - 1], 7), false);
    emit("gzip_cut_payload", 7, gzip(&gz[..gz.len() / 2], 7), false);
    emit(
        "gzip_one_tail",
        7,
        gzip(&[gz.as_slice(), b"x"].concat(), 7),
        false,
    );
    emit(
        "gzip_long_tail",
        7,
        gzip(&[gz.as_slice(), b"abcdefghijk"].concat(), 7),
        false,
    );
    emit(
        "gzip_zero_tail",
        7,
        gzip(&[gz.as_slice(), &[0]].concat(), 7),
        false,
    );
    emit("zlib_cut", 7, deflate(&zl[..zl.len() - 1], 7, true), false);
    let mut bad_adler = zl.clone();
    let last = bad_adler.len() - 1;
    bad_adler[last] ^= 1;
    emit("zlib_adler", 7, deflate(&bad_adler, 7, true), false);
    emit(
        "zlib_tail",
        7,
        deflate(&[zl.as_slice(), b"x"].concat(), 7, true),
        false,
    );
    emit(
        "raw_cut",
        7,
        deflate(&raw[..raw.len() - 1], 7, false),
        false,
    );
    emit(
        "raw_tail",
        7,
        deflate(&[raw.as_slice(), b"x"].concat(), 7, false),
        false,
    );
    emit("br_cut", 7, brotli(&br[..br.len() - 1], 7), false);
    emit(
        "br_tail",
        7,
        brotli(&[br.as_slice(), b"x"].concat(), 7),
        false,
    );
    emit(
        "br_second_stream",
        7,
        brotli(&[br.as_slice(), br.as_slice()].concat(), 7),
        false,
    );
    emit("zstd_cut", 7, zstd(&zs[..zs.len() - 1], 7), false);
    emit(
        "zstd_tail",
        7,
        zstd(&[zs.as_slice(), b"x"].concat(), 7),
        false,
    );
    emit(
        "zstd_frames",
        7,
        zstd(&[zs.as_slice(), zs.as_slice()].concat(), 7),
        true,
    );
    let skipped = [0x50u8, 0x2a, 0x4d, 0x18, 0, 0, 0, 0];
    emit(
        "zstd_skippable",
        1,
        zstd(&[zs.as_slice(), skipped.as_slice()].concat(), 1),
        true,
    );
    let high_window = [
        0x28u8, 0xb5, 0x2f, 0xfd, 0x00, 0x78, 0x11, 0x00, 0x00, b'o', b'k',
    ];
    emit("zstd_window25", 1, zstd(&high_window, 1), false);
    emit(
        "zstd_second_window25",
        7,
        zstd(&[zs.as_slice(), high_window.as_slice()].concat(), 7),
        false,
    );
    // stored block 的对齐填充位合法非零，构造开头与 zlib 头相同的 raw 流。
    let mut collision = vec![0x78, 0x9c, 0x00, 0x63, 0xff];
    collision.extend_from_slice(&[b'A'; 156]);
    collision.extend_from_slice(&[1, 0, 0, 255, 255]);
    emit(
        "raw_zlib_header_collision_raw",
        1,
        deflate(&collision, 1, false),
        true,
    );
    emit(
        "raw_zlib_header_collision_zlib",
        1,
        deflate(&collision, 1, true),
        false,
    );
}
