"""
Basic tests for BVD
"""

import tempfile
from pathlib import Path

from bvd import VersionDetector
from bvd.parsers.terraform import TerraformParser


def test_terraform_parser():
    """Test basic Terraform parsing"""
    parser = TerraformParser()
    
    # Test unbound version detection
    assert not parser.is_version_bound(">= 1.0.0")
    assert not parser.is_version_bound("*")
    assert parser.is_version_bound("~> 1.0.0")
    assert parser.is_version_bound("= 1.0.0")
    
    print("✅ Terraform parser tests passed")


def test_version_detector():
    """Test basic detector functionality"""
    detector = VersionDetector()
    
    # Should have terraform parser registered
    assert "Terraform" in detector.parsers
    
    print("✅ Version detector tests passed")


def test_terraform_file_parsing():
    """Test parsing a real Terraform file"""
    terraform_content = '''
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
  }
}
'''
    
    parser = TerraformParser()
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.tf', delete=False) as f:
        f.write(terraform_content)
        temp_path = Path(f.name)
    
    try:
        changes = parser.parse_dependencies(temp_path, terraform_content)
        
        # Should find 2 providers
        assert len(changes) == 2
        
        # Check AWS provider (unbound)
        aws_change = next(c for c in changes if "aws" in c.package_name)
        assert not parser.is_version_bound(aws_change.new_constraint)
        
        # Check Kubernetes provider (bound)
        k8s_change = next(c for c in changes if "kubernetes" in c.package_name)
        assert parser.is_version_bound(k8s_change.new_constraint)
        
        print("✅ Terraform file parsing tests passed")
        
    finally:
        temp_path.unlink()


def test_issue_detection():
    """Test issue detection on a real file"""
    terraform_content = '''
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0.0"
    }
  }
}
'''
    
    detector = VersionDetector()
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.tf', delete=False) as f:
        f.write(terraform_content)
        temp_path = Path(f.name)
    
    try:
        issues = detector.detect_issues([temp_path])
        
        # Should find 1 unbound version issue
        assert len(issues) == 1
        assert issues[0].issue_type.value == "unbound_version"
        assert "hashicorp/aws" in issues[0].message
        
        print("✅ Issue detection tests passed")
        
    finally:
        temp_path.unlink()


if __name__ == "__main__":
    test_terraform_parser()
    test_version_detector() 
    test_terraform_file_parsing()
    test_issue_detection()
    print("\n🎉 All tests passed!")