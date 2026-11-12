//! 私有控制入口，标准输出只承载已绑定的 JSONL。

use ccrb_tls_verifier::protocol::{Command, Event, Operation};
use ccrb_tls_verifier::relay::{Relay, profile};
use std::process;
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, BufReader, stdin};
use tokio::spawn;

#[tokio::main(worker_threads = 2)]
async fn main() {
    let mut lines = BufReader::new(stdin()).lines();
    let mut relay: Option<Arc<Relay>> = None;
    let mut listener = None;
    let mut instance = String::new();
    let mut last_command = 0;
    while let Ok(Some(line)) = lines.next_line().await {
        if line.len() > 512 * 1024 {
            break;
        }
        let Ok(command) = serde_json::from_str::<Command>(&line) else {
            break;
        };
        if command.schema_version != 1
            || command.command_id != last_command + 1
            || command.instance_id.is_empty()
        {
            break;
        }
        last_command = command.command_id;
        if relay.is_none() {
            let Operation::Init { config } = command.operation else {
                break;
            };
            instance = command.instance_id;
            let Ok((created, socket)) = Relay::create(instance.clone(), config).await else {
                break;
            };
            let Ok(address) = socket.local_addr() else {
                break;
            };
            created.emit(Event::Ready {
                command_id: command.command_id,
                profile: profile(),
                pid: process::id(),
                port: address.port(),
            });
            listener = Some(spawn(created.clone().listen(socket)));
            relay = Some(created);
            continue;
        }
        if command.instance_id != instance {
            break;
        }
        let current = relay.as_ref().unwrap();
        let result = match command.operation {
            Operation::Init { .. } => Err("already_initialized"),
            Operation::Begin { binding } => current.begin(binding),
            Operation::Expected { expected } => current.expected(expected),
            Operation::Finish {
                request_id,
                close_connections,
            } => current.finish(&request_id, close_connections).await,
            Operation::Shutdown => {
                if let Some(listener) = listener.take() {
                    listener.abort();
                }
                current.shutdown().await;
                current.emit(Event::Ack {
                    command_id: command.command_id,
                    error: None,
                });
                break;
            }
        };
        current.emit(Event::Ack {
            command_id: command.command_id,
            error: result.err(),
        });
    }
    if let Some(listener) = listener {
        listener.abort();
    }
    if let Some(relay) = relay {
        relay.shutdown().await;
    }
}
