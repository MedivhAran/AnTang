import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import type { ApiClient } from '../api/client';
import type { CaseGraph } from '../api/types';
import { colors, radii, spacing, typefaces } from '../ui/theme';

/**
 * 他自己说过的念头与情绪（只读）。
 *
 * 这些条目是对话里他自己讲出来的原话，系统只做归位与连线，不推断、不写诊断。
 * 所以这里没有编辑和删除：要改，得他在对话里再说一次。
 */

const LAYER_TITLES: Record<string, string> = {
  cognitive: '念头',
  affective: '情绪和身体',
};

export type CaseGraphSectionProps = {
  api: Pick<ApiClient, 'getCaseGraph'>;
};

export function CaseGraphSection({ api }: CaseGraphSectionProps) {
  const [graph, setGraph] = useState<CaseGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    let active = true;
    void api
      .getCaseGraph()
      .then((next) => {
        if (!active) return;
        setGraph(next);
        setLoadError(null);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setLoadError(error instanceof Error ? error.message : '读取失败');
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });
    return () => {
      active = false;
      mountedRef.current = false;
    };
  }, [api]);

  const textOf = (id: string): string => {
    const node = graph?.nodes.find((item) => item.id === id);
    return node === undefined ? '' : node.text;
  };

  return (
    <View style={styles.card}>
      <Text style={styles.title}>你和我说过的话</Text>
      <Text style={styles.hint}>
        这里只读：这些是你在对话里自己说出来的，系统只把它们归到念头或情绪下，不作诊断。要改，在对话里再说一次就行。
      </Text>
      {loading ? <ActivityIndicator color={colors.primary} /> : null}
      {loadError !== null ? <Text style={styles.error}>{loadError}</Text> : null}
      {!loading && loadError === null && (graph?.nodes.length ?? 0) === 0 ? (
        <Text style={styles.empty}>
          还没有记下什么。你讲过的念头和感受，会一条条记在这里。
        </Text>
      ) : null}
      {graph?.nodes.map((node) => (
        <View key={node.id} style={styles.row}>
          <Text style={styles.rowKind}>
            {LAYER_TITLES[node.layer] ?? node.layer} · {node.kindLabel}
          </Text>
          <Text style={styles.rowText}>
            {node.text}
            {node.intensity === null ? '' : `（强度 ${node.intensity}/5）`}
          </Text>
        </View>
      ))}
      {graph !== null && graph.edges.length > 0 ? (
        <View style={styles.edgeBlock}>
          <Text style={styles.rowKind}>他说过的因果关系</Text>
          {graph.edges.map((edge) => (
            <Text key={`${edge.fromNodeId}-${edge.toNodeId}`} style={styles.edgeText}>
              {textOf(edge.fromNodeId)} → {edge.relationLabel} →{' '}
              {textOf(edge.toNodeId)}
            </Text>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.paper,
    borderRadius: radii.lg,
    gap: spacing.sm,
    padding: spacing.lg,
  },
  title: {
    color: colors.ink,
    fontFamily: typefaces.serif,
    fontSize: 18,
  },
  hint: {
    color: colors.muted,
    fontFamily: typefaces.sans,
    fontSize: 13,
    lineHeight: 20,
  },
  empty: {
    color: colors.muted,
    fontFamily: typefaces.sans,
    fontSize: 14,
    lineHeight: 22,
  },
  error: {
    color: colors.danger,
    fontFamily: typefaces.sans,
    fontSize: 13,
  },
  row: {
    backgroundColor: colors.paperMuted,
    borderRadius: radii.md,
    gap: 2,
    padding: spacing.md,
  },
  rowKind: {
    color: colors.muted,
    fontFamily: typefaces.sans,
    fontSize: 12,
  },
  rowText: {
    color: colors.ink,
    fontFamily: typefaces.sans,
    fontSize: 15,
    lineHeight: 22,
  },
  edgeBlock: {
    gap: spacing.xs,
    paddingTop: spacing.xs,
  },
  edgeText: {
    color: colors.ink,
    fontFamily: typefaces.sans,
    fontSize: 13,
    lineHeight: 20,
  },
});
