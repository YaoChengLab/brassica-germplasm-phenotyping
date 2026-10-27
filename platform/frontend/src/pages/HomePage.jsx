import React from 'react';
import { Container, Card, Row, Col } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import DatabaseStats from '../components/DatabaseStats';
import '../App.css'; // For custom styles

function HomePage() {
  const cardStyle = {
    textDecoration: 'none',
    color: 'inherit',
    transition: 'transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out',
  };

  const handleMouseOver = (e) => {
    e.currentTarget.style.transform = 'translateY(-5px)';
    e.currentTarget.style.boxShadow = '0 8px 16px rgba(0,0,0,0.2)';
  };

  const handleMouseOut = (e) => {
    e.currentTarget.style.transform = 'translateY(0)';
    e.currentTarget.style.boxShadow = '0 4px 8px rgba(0,0,0,0.1)';
  };

  const FeatureCard = ({ to, icon, title, description }) => (
    <Link
      to={to}
      style={cardStyle}
      className="frosted-glass-card-kpi text-center h-100 d-flex flex-column justify-content-center align-items-center p-3"
      onMouseOver={handleMouseOver}
      onMouseOut={handleMouseOut}
    >
      <div style={{ fontSize: '3rem' }}>{icon}</div>
      <h5 className="mt-3">{title}</h5>
      <p>{description}</p>
    </Link>
  );

  return (
    <div className="home-background large-font-page">
      <Container className="d-flex flex-column align-items-center pt-5 pb-5">
        <Row className="justify-content-center w-100">
          <Col xs={12} md={10} lg={10} className="mb-5">
            <Card className="frosted-glass-card text-center">
              <Card.Header as="h5">Platform Features</Card.Header>
              <Card.Body>
                <Row>
                  <Col xs={12} md={4} className="mb-4">
                    <FeatureCard
                      to="/search-cultivars"
                      icon="🔍"
                      title="Cultivar Search"
                      description="Explore and filter through a comprehensive database of plant cultivars."
                    />
                  </Col>
                  <Col xs={12} md={4} className="mb-4">
                    <FeatureCard
                      to="/plant"
                      icon="🌿"
                      title="Plant Viewer"
                      description="Follow each plant through its single-plant images: trait time series, the image behind every point, and the leaf-ownership overlay used to check it."
                    />
                  </Col>
                  <Col xs={12} md={4} className="mb-4">
                    <FeatureCard
                      to="/export"
                      icon="📤"
                      title="Data Export"
                      description="Pick plants, traits and a time window; download a CSV that carries the business key and the sampling recipe for downstream analysis."
                    />
                  </Col>
                </Row>
              </Card.Body>
            </Card>
          </Col>
        </Row>
        <Row className="justify-content-center w-100">
          <Col xs={12} md={10} lg={10}>
            <DatabaseStats />
          </Col>
        </Row>
      </Container>
    </div>
  );
}

export default HomePage;
