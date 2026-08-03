import { useState, useEffect } from "react";
import { Modal } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { useDataSourcePreview } from "../../api/documents";
import { Loader2 } from "lucide-react";

export function DataSourceTableModal({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { data, isLoading, isError, error } = useDataSourcePreview(id);
  const [visibleCount, setVisibleCount] = useState(10);
  const notFoundMsg = (error as any)?.response?.data?.message ?? "No table preview available for this file.";

  // Reset count when target changes
  useEffect(() => {
    setVisibleCount(10);
  }, [id]);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const target = e.currentTarget;
    if (target.scrollHeight - target.scrollTop <= target.clientHeight + 25) {
      if (data && visibleCount < data.sampleRows.length) {
        setVisibleCount((prev) => Math.min(prev + 10, data.sampleRows.length));
      }
    }
  };

  return (
    <Modal open={!!id} onClose={onClose} width={760}>
      {isLoading && (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: 300, gap: 12 }}>
          <Loader2 size={32} style={{ animation: "dvspin 1.5s linear infinite", color: "var(--ac)" }} />
          <div style={{ fontSize: 13, color: "#9499ad" }}>Loading preview...</div>
        </div>
      )}
      {isError && (
        <div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <div style={{ font: "600 12px 'IBM Plex Mono',monospace", fontWeight: 700 }}>Preview unavailable</div>
            <button onClick={onClose} style={{ fontSize: 16, color: "#9499ad" }}>
              ✕
            </button>
          </div>
          <p style={{ fontSize: 13, color: "#71768a" }}>{notFoundMsg}</p>
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 16 }}>
            <Button variant="secondary" onClick={onClose}>
              Close
            </Button>
          </div>
        </div>
      )}
      {!isLoading && data && (
        <>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
            <div>
              <div style={{ font: "600 12px 'IBM Plex Mono',monospace", fontWeight: 700 }}>{data.title}</div>
              <div style={{ fontSize: 11.5, color: "#9499ad" }}>
                {data.filename} · {data.columns.length} cols · {(data.rowCount ?? 0).toLocaleString()} rows
              </div>
            </div>
            <button onClick={onClose} style={{ fontSize: 16, color: "#9499ad" }}>
              ✕
            </button>
          </div>
          
          <div 
            onScroll={handleScroll}
            style={{ 
              overflowX: "auto", 
              overflowY: "auto",
              maxHeight: "360px",
              marginTop: 14, 
              border: "1px solid #e9eaf2", 
              borderRadius: 10 
            }}
          >
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ background: "#f7f8fc" }}>
                  {data.columns.map((c) => (
                    <th key={c} style={{ padding: "8px 12px", textAlign: "left", fontWeight: 700, whiteSpace: "nowrap", position: "sticky", top: 0, background: "#f7f8fc", zIndex: 10 }}>
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.sampleRows.slice(0, visibleCount).map((row, i) => (
                  <tr key={i} style={{ borderTop: "1px solid #f0f1f6" }}>
                    {row.map((cell, j) => (
                      <td key={j} style={{ padding: "8px 12px", fontFamily: "'IBM Plex Mono',monospace", whiteSpace: "nowrap" }}>
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>

            {visibleCount < data.sampleRows.length && (
              <div style={{ padding: "10px", textAlign: "center", fontSize: 11, color: "#9499ad", background: "#fafafa", borderTop: "1px solid #f0f1f6" }}>
                Scroll down to load more rows...
              </div>
            )}
          </div>

          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 12 }}>
            <div style={{ fontSize: 11, color: "#9499ad" }}>
              Showing {Math.min(visibleCount, data.sampleRows.length)} of {(data.rowCount ?? data.sampleRows.length).toLocaleString()} rows · read-only preview
            </div>
            <Button variant="secondary" onClick={onClose}>
              Close
            </Button>
          </div>
        </>
      )}
    </Modal>
  );
}
