//! 任务账号代理选择的公开桥，私有连接只传给原运行时维护接口。
use std::collections::{HashMap, HashSet};
use std::time::Duration;

use axum::Json;
use axum::body::Bytes;
use axum::http::{HeaderMap, Method, StatusCode, header};
use axum::response::{IntoResponse, Response};
use serde::Deserialize;
use serde_json::{Value, json};

use crate::error::AppError;
use crate::handler::router::AppState;
use crate::model::proxy::{ProxyConnection, ProxyConnectionInput};
use crate::store::proxy_store::ProxyRecord;

/// 只接受明确目录选择与原快照版本。
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SelectionInput {
    selection_revision: String,
    proxy_id: Value,
    proxy_revision: Option<String>,
}

/// 解析唯一任务路径，拒绝零、负数及额外路径段。@param path 桥内路径。@return 正任务ID。
pub(super) fn identity(path: &str) -> Option<i64> {
    let raw = path
        .strip_prefix("/api/accounts/")?
        .strip_suffix("/proxy-selection")?;
    let id = raw.parse::<i64>().ok()?;
    (id > 0 && id.to_string() == raw).then_some(id)
}

fn summary(connection: Option<&ProxyConnection>, records: &[ProxyRecord]) -> Value {
    let Some(connection) = connection else {
        return json!({"kind":"direct","name":"直连","public_url":"","status":"unknown","observation":null});
    };
    if let Some(record) = records
        .iter()
        .find(|row| row.connection.private_url == connection.private_url)
    {
        return json!({"kind":"directory","id":record.id,"name":record.name,"revision":record.revision,
            "public_url":record.connection.public_url,"status":record.status,"observation":record.observation,
            "checked_at":record.checked_at,"expires_at":record.expires_at});
    }
    json!({"kind":"custom","name":"自定义线路","public_url":connection.public_url,"status":"unknown","observation":null})
}

async fn public_snapshot(state: &AppState, value: Value, id: i64) -> Result<Value, AppError> {
    if value["account_id"].as_i64() != Some(id) {
        return Err(AppError::ServiceUnavailable(
            "任务代理身份不一致，请重新读取".into(),
        ));
    }
    let revision = value["selection_revision"]
        .as_str()
        .filter(|s| s.len() == 64 && s.bytes().all(|c| c.is_ascii_hexdigit()))
        .ok_or_else(|| AppError::ServiceUnavailable("任务代理版本暂不可读取".into()))?;
    let raw = value["connection"]
        .as_str()
        .ok_or_else(|| AppError::ServiceUnavailable("任务代理配置暂不可读取".into()))?;
    let connection = if raw.is_empty() {
        None
    } else {
        Some(ProxyConnection::parse(raw)?)
    };
    let records = state
        .proxy_svc
        .store
        .matching(
            &connection
                .iter()
                .map(|c| c.private_url.clone())
                .collect::<Vec<_>>(),
        )
        .await?;
    Ok(
        json!({"account_id":id,"name":value["name"],"gateway_account_id":value["gateway_account_id"],
        "selection_revision":revision,"current":summary(connection.as_ref(), &records)}),
    )
}

/// 有界读取任务管理JSON，禁止透传私有接口原始错误。@param response 内部响应。@return JSON。
async fn bounded_json(mut response: reqwest::Response) -> Result<Value, AppError> {
    let mut bytes = Vec::new();
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|_| AppError::ServiceUnavailable("任务代理读取中断".into()))?
    {
        if bytes.len() + chunk.len() > 4 * 1024 * 1024 {
            return Err(AppError::ServiceUnavailable(
                "任务代理响应超出读取范围".into(),
            ));
        }
        bytes.extend_from_slice(&chunk);
    }
    serde_json::from_slice(&bytes)
        .map_err(|_| AppError::ServiceUnavailable("任务代理响应格式无效".into()))
}

/// 已通过原会话与来源校验后，持有目录锁完成一次选择事务。
/// @param state 应用服务。@param id 任务ID。@param method 读取或保存。@param body 浏览器载荷。@param headers 原会话头。
/// @return 只包含公开字段的选择快照。
pub(super) async fn selection(
    state: AppState,
    id: i64,
    method: Method,
    body: Bytes,
    headers: HeaderMap,
) -> Result<Response, AppError> {
    if !matches!(method, Method::GET | Method::PUT) {
        return Err(AppError::NotFound);
    }
    let mut guard = if method == Method::PUT {
        Some(state.proxy_svc.mutations.clone().lock_owned().await)
    } else {
        None
    };
    let mut ticket = None;
    let payload = if method == Method::PUT {
        let input: SelectionInput = serde_json::from_slice(&body)
            .map_err(|_| AppError::BadRequest("请选择有效代理并重新读取账号版本".into()))?;
        if input.selection_revision.len() != 64
            || !input
                .selection_revision
                .bytes()
                .all(|c| c.is_ascii_hexdigit())
        {
            return Err(AppError::BadRequest("账号代理版本无效，请重新读取".into()));
        }
        let connection = if input.proxy_id.is_null() {
            if input.proxy_revision.is_some() {
                return Err(AppError::BadRequest("直连选择不接受线路版本".into()));
            }
            String::new()
        } else {
            let proxy = state
                .proxy_svc
                .store
                .get(
                    input
                        .proxy_id
                        .as_str()
                        .ok_or_else(|| AppError::BadRequest("代理选择无效".into()))?,
                )
                .await?;
            if input.proxy_revision.as_deref() != Some(&proxy.revision) {
                return Err(AppError::BadRequest("所选代理已变化，请重新选择".into()));
            }
            proxy.connection.private_url
        };
        ticket = Some(
            state.proxy_svc.task_selections.reserve(
                id,
                &input.selection_revision,
                &connection,
                guard
                    .take()
                    .ok_or_else(|| AppError::ServiceUnavailable("代理配置许可缺失".into()))?,
            )?,
        );
        Some(
            json!({"selection_revision":input.selection_revision,"connection":connection,"operation_id":ticket.as_ref().map(|value| &value.id)}),
        )
    } else {
        None
    };
    let (base, token, client) = super::config()?;
    let mut request = client
        .request(method, format!("{base}/api/accounts/{id}/proxy-selection"))
        .bearer_auth(token)
        .header(header::COOKIE, super::cookie(&headers))
        .timeout(Duration::from_secs(45));
    if let Some(payload) = payload {
        request = request.json(&payload);
    }
    let response = request.send().await.map_err(|_| {
        AppError::ServiceUnavailable("代理切换结果待核对，请重新读取当前配置".into())
    })?;
    // 票据必须覆盖响应读取与公开投影；网络错误退出时撤销尚未领取的请求。
    let _ticket = ticket;
    if !response.status().is_success() {
        let status = match response.status() {
            StatusCode::NOT_FOUND => StatusCode::NOT_FOUND,
            StatusCode::CONFLICT | StatusCode::BAD_REQUEST => StatusCode::CONFLICT,
            _ => StatusCode::SERVICE_UNAVAILABLE,
        };
        let error = bounded_json(response).await.ok();
        let code = error
            .as_ref()
            .and_then(|value| value["detail"]["code"].as_str());
        let message = if status == StatusCode::NOT_FOUND {
            "任务账号已不可用"
        } else if status == StatusCode::CONFLICT {
            match code {
                Some("busy") => "账号仍有任务、请求或授权进行中，请等待结束后重试",
                Some("disabled") => "任务账号已停用，请先核对账号状态",
                Some("changed") => "账号关联或代理配置已变化，请重新读取后选择",
                _ => "代理切换未完成，请核对账号状态并重新读取配置",
            }
        } else {
            "代理配置暂不可读取，请稍后重试"
        };
        return Ok((status, Json(json!({"error":message}))).into_response());
    }
    Ok(Json(public_snapshot(&state, bounded_json(response).await?, id).await?).into_response())
}

/// 一次批量投影任务线路，匹配失败保留明确未知，不影响其它任务资料。
/// @param state 服务。@param response 原任务列表。@return 附加公开目录摘要的列表。
pub(super) async fn accounts(
    state: &AppState,
    response: reqwest::Response,
) -> Result<Response, AppError> {
    if !response.status().is_success() {
        return Ok(super::response(response));
    }
    let mut values = bounded_json(response).await?;
    let rows = values
        .as_array_mut()
        .ok_or_else(|| AppError::ServiceUnavailable("任务账号列表格式无效".into()))?;
    let gateways = state
        .account_svc
        .list_accounts()
        .await
        .ok()
        .map(|accounts| {
            accounts
                .into_iter()
                .map(|a| (a.id, a.proxy_url))
                .collect::<HashMap<_, _>>()
        });
    let connections = rows
        .iter()
        .map(|row| {
            if let Some(id) = row["cc2api_account_id"].as_i64() {
                let raw = gateways.as_ref()?.get(&id)?;
                if raw.is_empty() {
                    return Some(None);
                }
                return ProxyConnection::parse(raw).ok().map(Some);
            }
            let host = row["upstream_socks5_host"].as_str().unwrap_or_default();
            if host.trim().is_empty() {
                return Some(None);
            }
            let protocol = row["upstream_proxy_scheme"].as_str().unwrap_or("socks5");
            let input = ProxyConnectionInput {
                protocol: protocol.into(),
                host: host.into(),
                port: u16::try_from(
                    row["upstream_socks5_port"]
                        .as_u64()
                        .unwrap_or(if protocol == "http" { 80 } else { 1080 }),
                )
                .ok()?,
                username: Some(
                    row["upstream_socks5_user"]
                        .as_str()
                        .unwrap_or_default()
                        .into(),
                ),
                password: Some(
                    row["upstream_socks5_pass"]
                        .as_str()
                        .unwrap_or_default()
                        .into(),
                ),
            };
            ProxyConnection::from_input(&input, None).ok().map(Some)
        })
        .collect::<Vec<_>>();
    let unique = connections
        .iter()
        .flatten()
        .flatten()
        .map(|c| c.private_url.clone())
        .collect::<HashSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    let records = state.proxy_svc.store.matching(&unique).await;
    for (row, connection) in rows.iter_mut().zip(&connections) {
        row["proxy_selection"] = match (connection, &records) {
            (Some(connection), Ok(records)) => summary(connection.as_ref(), records),
            _ => {
                json!({"kind":"unknown","name":"代理待读取","public_url":"","status":"unknown","observation":null})
            }
        };
    }
    Ok(Json(values).into_response())
}

#[cfg(test)]
mod tests {
    use super::{SelectionInput, identity, summary};
    use crate::model::proxy::ProxyConnection;
    use crate::store::proxy_store::ProxyRecord;
    use serde_json::{Value, json};

    #[test]
    fn task_proxy_path_and_payload_are_explicit() {
        assert_eq!(identity("/api/accounts/12/proxy-selection"), Some(12));
        for path in [
            "/api/accounts/0/proxy-selection",
            "/api/accounts/01/proxy-selection",
            "/api/accounts/-1/proxy-selection",
            "/api/accounts/1/other/proxy-selection",
        ] {
            assert_eq!(identity(path), None);
        }
        let revision = "a".repeat(64);
        for value in [
            json!({"selection_revision":revision}),
            json!({"proxy_id":null}),
            json!({"selection_revision":revision,"proxy_id":null,"connection":"private"}),
        ] {
            assert!(serde_json::from_value::<SelectionInput>(value).is_err());
        }
        assert!(
            serde_json::from_value::<SelectionInput>(
                json!({"selection_revision":revision,"proxy_id":null})
            )
            .is_ok()
        );
    }

    #[test]
    fn summary_matches_private_identity_and_exposes_only_public_fields() {
        let connection =
            ProxyConnection::parse("http://synthetic-user:synthetic-secret@proxy.invalid:8080")
                .unwrap();
        let record = ProxyRecord {
            id: "route-1".into(),
            name: "主线路".into(),
            connection: connection.clone(),
            expires_at: None,
            revision: "revision-1".into(),
            observation: None,
            checked_at: None,
            status: "unknown".into(),
            created_at: "time".into(),
            updated_at: "time".into(),
        };
        let records = [record];
        let public = summary(Some(&connection), &records);
        assert_eq!(public["kind"], "directory");
        assert_eq!(public["name"], "主线路");
        assert_eq!(public["public_url"], "http://proxy.invalid:8080");
        assert!(!public.to_string().contains("synthetic"));
        assert_eq!(public["password"], Value::Null);
        let different = ProxyConnection::parse("http://other:secret@proxy.invalid:8080").unwrap();
        assert_eq!(summary(Some(&different), &records)["kind"], "custom");
        assert_eq!(summary(None, &records)["kind"], "direct");
    }
}
