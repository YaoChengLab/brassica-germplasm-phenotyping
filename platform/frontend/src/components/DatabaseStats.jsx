import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Spinner } from 'react-bootstrap';
import { apiV2 } from '../services/api';

const QC_STATUS_LABEL = {
    verified: 'verified',
    auto: 'auto',
    no: 'not reviewed',
};

const fmt = (n) => (n ?? 0).toLocaleString();

const Kpi = ({ icon, value, label }) => (
    <Card className="frosted-glass-card-kpi text-center h-100">
        <Card.Body>
            <div style={{ fontSize: '2.5rem' }}>{icon}</div>
            <Card.Title className="mt-2">{value}</Card.Title>
            <Card.Text className="mb-0">{label}</Card.Text>
        </Card.Body>
    </Card>
);

const DatabaseStats = () => {
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchStats = async () => {
            try {
                const summary = await apiV2.get('/query/plant/summary');
                setStats(summary.data);
            } catch (error) {
                console.error("Error fetching database stats:", error);
            } finally {
                setLoading(false);
            }
        };

        fetchStats();
    }, []);

    if (loading) {
        return <Spinner animation="border" variant="light" />;
    }

    if (!stats) {
        return null;
    }

    const qc = stats.observations_by_qc_status || {};
    // Ordered strongest-claim-first: a reviewed count is the one that carries
    // weight, so it leads even though it is the smaller number.
    const qcSummary = ['verified', 'auto', 'no']
        .filter((k) => qc[k])
        .map((k) => `${fmt(qc[k])} ${QC_STATUS_LABEL[k]}`)
        .join(' · ');

    return (
        <Card className="frosted-glass-card text-center">
            <Card.Header as="h5">Database Statistics</Card.Header>
            <Card.Body>
                {/* Summary KPIs */}
                <Row className="mb-2">
                    <Col><Kpi icon="🍀" value={fmt(stats.total_cultivars)} label="Cultivars" /></Col>
                    <Col><Kpi icon="🌱" value={fmt(stats.total_plants)} label="Plants" /></Col>
                    <Col><Kpi icon="📦" value={fmt(stats.total_batches)} label="Batches" /></Col>
                    <Col><Kpi icon="🔬" value={fmt(stats.total_observations)} label="Observations" /></Col>
                </Row>

                {/* Full-width caption rather than a fourth line inside the KPI
                    card: at card width the three parts wrap and leave that one
                    card visibly taller than its neighbours. */}
                {qcSummary && (
                    <p className="small text-muted mb-0">
                        Observations are QC-classified: {qcSummary}
                    </p>
                )}
            </Card.Body>
        </Card>
    );
};

export default DatabaseStats;
