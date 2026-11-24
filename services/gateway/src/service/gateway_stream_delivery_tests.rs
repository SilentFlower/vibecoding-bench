/// 在随机回环端口运行路由，保留真实的 HTTP 分块和套接字调度。
/// @param app 要公开的路由。@return HTTP 根地址和服务任务。
async fn serve_stream_test_router(app: Router) -> (String, JoinHandle<()>) {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("http://{}", listener.local_addr().unwrap());
    let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    (url, server)
}

/// 把模型事件编码为独立 SSE 帧。
/// @param data 含事件类型的 JSON。@return 包含结束空行的帧。
fn stream_test_frame(data: Value) -> String {
    format!(
        "event: {}\ndata: {data}\n\n",
        data["type"].as_str().unwrap()
    )
}

/// 从真实客户端读到本次控制帧结束，跨越任意 HTTP 字节边界。
/// @param response 客户端响应。@param received 累计实收字节。@param marker 本阶段末帧。
async fn read_stream_test_marker(
    response: &mut reqwest::Response,
    received: &mut Vec<u8>,
    marker: &str,
) {
    let from = received.len();
    while !received[from..]
        .windows(marker.len())
        .any(|bytes| bytes == marker.as_bytes())
    {
        let chunk = response
            .chunk()
            .await
            .unwrap()
            .expect("控制帧之前响应流已关闭");
        received.extend_from_slice(&chunk);
    }
}

/// 用两个独立暂停点核验公开 Messages 路由，并让同样发送心跳的缓冲对照经过同一路径。
/// @return 正文在放行前可见、两条路径的最终字节一致且每个请求只抵达模型一次时通过。
#[tokio::test]
async fn public_messages_stream_delivers_each_delta_before_source_continues() {
    let (submissions, mut source) = mpsc::unbounded_channel();
    let upstream = Router::new().route(
        "/v1/messages",
        post(move |Json(payload): Json<Value>| {
            let submissions = submissions.clone();
            async move {
                assert_eq!(payload["stream"], true);
                let (send, recv) = mpsc::channel::<Bytes>(1);
                submissions.send(send).unwrap();
                let body = Body::from_stream(ReceiverStream::new(recv).map(Ok::<_, Infallible>));
                ([(CONTENT_TYPE, "text/event-stream")], body)
            }
        }),
    );
    let (origin, model_server) = serve_stream_test_router(upstream).await;
    let service = Arc::new(test_gateway_service_with_urls(origin, String::new()).await);
    create_setup_gateway_account(&service, "stream@example.invalid", "synthetic-stream", 50).await;
    let (router, token) = authenticated_gateway_router(service).await;
    let (gateway, public_server) = serve_stream_test_router(router).await;
    let client = reqwest::Client::builder().no_proxy().build().unwrap();

    let text_block = json!({"type":"text","text":""});
    let text_deltas = [1, 2].map(|stage| {
        json!({
            "type":"text_delta","text":format!("第{stage}段\n{}", uuid::Uuid::new_v4())
        })
    });
    let tool_block = json!({"type":"tool_use","id":"toolu_local","name":"Read","input":{}});
    let partials = [
        r#"{"path":"#.to_owned(),
        format!(r#""{}.txt"}}"#, uuid::Uuid::new_v4()),
    ];
    assert!(serde_json::from_str::<Value>(&partials[0]).is_err());
    assert!(serde_json::from_str::<Value>(&partials.concat()).unwrap()["path"].is_string());
    let tool_deltas = partials.map(|part| json!({"type":"input_json_delta","partial_json":part}));
    for (buffered, block, deltas, stop_reason) in [
        (false, &text_block, &text_deltas, "end_turn"),
        (true, &text_block, &text_deltas, "end_turn"),
        (false, &tool_block, &tool_deltas, "tool_use"),
    ] {
        // 超时只用来报失败。每一次放行由客户端实际读到的事件驱动。
        timeout(Duration::from_secs(10), async {
            let request = client.post(format!("{gateway}/v1/messages"))
                .header("x-api-key", &token.token)
                .header("user-agent", "python-httpx/0.28.1")
                .json(&json!({"model":"claude-sonnet-5-5","stream":true,"max_tokens":64,
                    "messages":[{"role":"user","content":"测试流式回复"}],
                    "tools":[{"name":"Read","input_schema":{"type":"object","properties":{"path":{"type":"string"}}}}]}))
                .send();
            let pending = tokio::spawn(request);
            let writer = source.recv().await.unwrap();
            let message = json!({"id":"msg_stream_test","type":"message","role":"assistant",
                "model":"claude-sonnet-5-5","content":[],"stop_reason":null,"stop_sequence":null,
                "usage":{"input_tokens":6,"output_tokens":0}});
            let start = stream_test_frame(json!({"type":"message_start","message":message}))
                + &stream_test_frame(json!({"type":"content_block_start","index":0,
                    "content_block":block}));
            writer.send(Bytes::from(start.clone())).await.unwrap();
            let mut response = pending.await.unwrap().unwrap();
            assert_eq!(response.status(), StatusCode::OK);
            assert_eq!(response.headers()[CONTENT_TYPE], "text/event-stream");
            let mut received = Vec::new();
            let mut expected = start;
            let mut held = String::new();
            for (index, value) in deltas.iter().enumerate() {
                let delta = stream_test_frame(json!({"type":"content_block_delta","index":0,
                    "delta":value}));
                // 带序号的心跳仅供夹具确定本阶段已抵达。正文仍需独立按完整帧核对。
                let marker = stream_test_frame(json!({"type":"ping","stage":index + 1}));
                if buffered {
                    held.push_str(&delta);
                } else {
                    writer.send(Bytes::from(delta.clone())).await.unwrap();
                    expected.push_str(&delta);
                    // 此时上游连下一帧心跳都没有生成，客户端必须能单独读到正文。
                    read_stream_test_marker(&mut response, &mut received, &delta).await;
                }
                writer.send(Bytes::from(marker.clone())).await.unwrap();
                expected.push_str(&marker);
                read_stream_test_marker(&mut response, &mut received, &marker).await;
                assert_eq!(received.windows(delta.len()).any(|bytes| bytes == delta.as_bytes()), !buffered);
            }
            let end = held
                + &stream_test_frame(json!({"type":"content_block_stop","index":0}))
                + &stream_test_frame(json!({"type":"message_delta",
                    "delta":{"stop_reason":stop_reason,"stop_sequence":null},"usage":{"output_tokens":2}}))
                + &stream_test_frame(json!({"type":"message_stop"}));
            expected.push_str(&end);
            writer.send(Bytes::from(end)).await.unwrap();
            drop(writer);
            received.extend_from_slice(&response.bytes().await.unwrap());
            assert_eq!(received, expected.as_bytes());
            assert!(source.try_recv().is_err(), "每个请求只能提交一次");
        }).await.expect("公开入口未在模型等待期间交付预期帧");
    }
    public_server.abort();
    model_server.abort();
}
